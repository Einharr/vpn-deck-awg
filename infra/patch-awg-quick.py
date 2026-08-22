#!/usr/bin/env python3
"""Apply the SteamOS endpoint underlay-route fix to upstream awg-quick.

The patch is intentionally structural rather than a long-lived fork of the
script. It fails loudly if upstream changes the expected anchors.
"""

from __future__ import annotations

import pathlib
import sys


PATCH_MARKER = "vpn-deck-awg: endpoint-direct-route"
FUNCTIONS = r'''
# vpn-deck-awg: endpoint-direct-route
ENDPOINT_ROUTE_STATE_DIR="/var/run/awg-quick"

_endpoint_route_state_file() {
    echo "$ENDPOINT_ROUTE_STATE_DIR/${INTERFACE}.endpoint-routes"
}

set_endpoint_direct_route() {
    local endpoint host proto mask route_info gw dev state_file
    state_file="$(_endpoint_route_state_file)"
    mkdir -p "$ENDPOINT_ROUTE_STATE_DIR" 2>/dev/null || return 0
    : > "$state_file" 2>/dev/null || return 0
    while read -r _ endpoint; do
        [[ $endpoint =~ ^\[?([a-z0-9:.]+)\]?:[0-9]+$ ]] || continue
        host="${BASH_REMATCH[1]}"
        if [[ $host == *:* ]]; then
            proto=-6; mask=128
        else
            proto=-4; mask=32
        fi
        route_info="$(ip $proto route get "$host" 2>/dev/null | head -n1)"
        [[ -n $route_info ]] || continue
        [[ $route_info =~ via\ ([^ ]+) ]] || continue
        gw="${BASH_REMATCH[1]}"
        [[ $route_info =~ dev\ ([^ ]+) ]] || continue
        dev="${BASH_REMATCH[1]}"
        [[ $dev != "$INTERFACE" ]] || continue
        if cmd ip $proto route replace "$host/$mask" via "$gw" dev "$dev"; then
            echo "$proto $host/$mask" >> "$state_file"
        fi
    done < <(awg show "$INTERFACE" endpoints 2>/dev/null)
    [[ -s $state_file ]] || rm -f "$state_file"
}

del_endpoint_direct_route() {
    local proto cidr state_file
    state_file="$(_endpoint_route_state_file)"
    [[ -f $state_file ]] || return 0
    while read -r proto cidr; do
        [[ -n $proto && -n $cidr ]] || continue
        cmd ip $proto route del "$cidr" 2>/dev/null || true
    done < "$state_file"
    rm -f "$state_file"
}
'''.lstrip()


DNS_STEAMOS = '''HAVE_SET_DNS=0
set_dns() {
\t[[ ${#DNS[@]} -gt 0 ]] || return 0
\tcmd resolvectl dns "$INTERFACE" "${DNS[@]}"
\t[[ ${#DNS_SEARCH[@]} -eq 0 ]] || cmd resolvectl domain "$INTERFACE" "${DNS_SEARCH[@]}"
\tHAVE_SET_DNS=1
}

unset_dns() {
\t[[ ${#DNS[@]} -gt 0 ]] || return 0
\tcmd resolvectl revert "$INTERFACE"
}
'''

def replace_once(text: str, needle: str, replacement: str) -> str:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"expected one patch anchor, found {count}: {needle[:80]!r}")
    return text.replace(needle, replacement, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch-awg-quick.py PATH", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        return 0

    # SteamOS uses systemd-resolved/resolvectl rather than openresolv.
    if "cmd resolvectl dns" not in text:
        dns_start = text.find("resolvconf_iface_prefix() {")
        dns_end = text.find("add_route() {", dns_start)
        if dns_start < 0 or dns_end < 0:
            raise RuntimeError("could not find upstream DNS block")
        text = text[:dns_start] + DNS_STEAMOS + "\n" + text[dns_end:]

    text = replace_once(
        text,
        '\tcmd ip link delete dev "$INTERFACE"\n',
        '\tdel_endpoint_direct_route || true\n\tcmd ip link delete dev "$INTERFACE"\n',
    )
    text = replace_once(text, "save_config() {\n", FUNCTIONS + "\nsave_config() {\n")

    route_loop = '\tfor i in $(while read -r _ i; do for i in $i; do [[ $i =~ ^[0-9a-z:.]+/[0-9]+$ ]] && echo "$i"; done; done < <(awg show "$INTERFACE" allowed-ips) | sort -nr -k 2 -t /); do\n'
    text = replace_once(
        text,
        route_loop,
        '\t# Preserve a direct underlay route to peer endpoints before the tunnel changes routing.\n\tset_endpoint_direct_route\n' + route_loop,
    )

    path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
