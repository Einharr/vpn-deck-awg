"""Protocol detection and safe metadata extraction for WireGuard/AmneziaWG configs."""

from __future__ import annotations

import base64
import ipaddress
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple


AWG1_KEYS = {
    "jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4",
}
AWG15_KEYS = {"i1"}
AWG2_KEYS = {"s3", "s4", "i2", "i3", "i4", "i5"}
AWG3_KEYS = {
    "headerprotectionkey",
    "contentpaddingaddition",
    "rekeyaftertime",
    "rekeytimeout",
    "rejectaftertime",
    "keepalivetimeout",
    "maxhandshakeattempts",
}

PROTOCOL_LABELS = {
    "wireguard": "WireGuard",
    "awg-1.0": "AmneziaWG 1.0",
    "awg-1.5": "AmneziaWG 1.5",
    "awg-2.0": "AmneziaWG 2.0",
    "awg-3.0": "AmneziaWG 3.0",
}

# Common keys accepted by wg-quick/awg-quick and the underlying tool. Unknown
# keys are not rejected here so newer AmneziaWG configs remain forward-compatible.
SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KEY_VALUE_RE = re.compile(r"^\s*([^=]+?)\s*=\s*(.*?)\s*$")


@dataclass
class ConfigAnalysis:
    valid: bool
    protocol: str
    protocol_label: str
    errors: List[str]
    warnings: List[str]
    address: List[str]
    dns: List[str]
    mtu: Optional[str]
    peer_count: int
    endpoints: List[str]
    allowed_ips: List[str]
    full_tunnel: bool
    has_ipv6: bool
    persistent_keepalive: bool

    def to_dict(self) -> Dict:
        return asdict(self)


def _split_csv(value: str) -> List[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _valid_wg_key(value: str) -> bool:
    try:
        decoded = base64.b64decode(value.strip(), validate=True)
    except Exception:
        return False
    return len(decoded) == 32


def _parse(content: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """Return (section, key, value) tuples without exposing comments."""
    entries: List[Tuple[str, str, str]] = []
    errors: List[str] = []
    section = ""

    for line_no, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        match = SECTION_RE.match(raw)
        if match:
            section = match.group(1).strip().lower()
            continue

        match = KEY_VALUE_RE.match(raw)
        if not match:
            errors.append(f"Line {line_no}: expected key = value")
            continue

        if not section:
            errors.append(f"Line {line_no}: key outside a section")
            continue

        key = match.group(1).strip()
        value = match.group(2).strip()
        entries.append((section, key, value))

    return entries, errors


def detect_protocol(content: str) -> str:
    entries, _ = _parse(content)
    interface_keys = {key.lower() for section, key, _ in entries if section == "interface"}

    if interface_keys & AWG3_KEYS:
        return "awg-3.0"
    if interface_keys & AWG2_KEYS:
        return "awg-2.0"
    if interface_keys & AWG15_KEYS:
        return "awg-1.5"
    if interface_keys & AWG1_KEYS:
        return "awg-1.0"
    return "wireguard"


def analyse_config(content: str) -> Dict:
    """Validate enough for safe import and return non-secret UI metadata.

    This deliberately does not reject unknown keys. AmneziaWG evolves faster
    than the plugin; the bundled awg-tools remains the final parser authority.
    """
    entries, parse_errors = _parse(content)
    errors = list(parse_errors)
    warnings: List[str] = []

    sections = [section for section, _, _ in entries]
    interface_entries = [(key, value) for section, key, value in entries if section == "interface"]
    peer_groups: List[List[Tuple[str, str]]] = []
    current_peer: Optional[List[Tuple[str, str]]] = None

    # Re-scan lines so repeated [Peer] sections remain distinct.
    current_section = ""
    for raw in content.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        section_match = SECTION_RE.match(raw)
        if section_match:
            current_section = section_match.group(1).strip().lower()
            if current_section == "peer":
                current_peer = []
                peer_groups.append(current_peer)
            else:
                current_peer = None
            continue
        kv_match = KEY_VALUE_RE.match(raw)
        if kv_match and current_section == "peer" and current_peer is not None:
            current_peer.append((kv_match.group(1).strip(), kv_match.group(2).strip()))

    if "interface" not in sections:
        errors.append("Missing [Interface] section")

    interface_map = {key.lower(): value for key, value in interface_entries}
    private_key = interface_map.get("privatekey")
    if not private_key:
        errors.append("Missing Interface PrivateKey")
    elif not _valid_wg_key(private_key):
        errors.append("Interface PrivateKey is not a valid WireGuard key")

    addresses = _split_csv(interface_map.get("address", ""))
    dns = _split_csv(interface_map.get("dns", ""))
    mtu = interface_map.get("mtu") or None

    has_ipv6 = False
    for address in addresses:
        try:
            network = ipaddress.ip_interface(address)
            has_ipv6 = has_ipv6 or network.version == 6
        except ValueError:
            warnings.append(f"Address looks unusual: {address}")

    if not peer_groups:
        errors.append("Missing [Peer] section")

    endpoints: List[str] = []
    allowed_ips: List[str] = []
    persistent_keepalive = False

    for index, peer in enumerate(peer_groups, start=1):
        peer_map = {key.lower(): value for key, value in peer}
        public_key = peer_map.get("publickey")
        if not public_key:
            errors.append(f"Peer {index}: missing PublicKey")
        elif not _valid_wg_key(public_key):
            errors.append(f"Peer {index}: PublicKey is not a valid WireGuard key")

        preshared_key = peer_map.get("presharedkey")
        if preshared_key and preshared_key != "(none)" and not _valid_wg_key(preshared_key):
            errors.append(f"Peer {index}: PresharedKey is not a valid WireGuard key")

        endpoint = peer_map.get("endpoint")
        if endpoint:
            endpoints.append(endpoint)
        else:
            warnings.append(f"Peer {index}: no Endpoint (valid for inbound/server peers)")

        peer_allowed = _split_csv(peer_map.get("allowedips", ""))
        if not peer_allowed:
            warnings.append(f"Peer {index}: no AllowedIPs")
        allowed_ips.extend(peer_allowed)

        keepalive = peer_map.get("persistentkeepalive", "").strip().lower()
        if keepalive and keepalive not in {"0", "off"}:
            persistent_keepalive = True

    full_tunnel = any(ip in {"0.0.0.0/0", "::/0"} for ip in allowed_ips)
    protocol = detect_protocol(content)

    if protocol != "wireguard":
        missing_core = [key for key in ("jc", "jmin", "jmax") if key not in interface_map]
        if missing_core:
            warnings.append("AmneziaWG config is missing: " + ", ".join(missing_core))

    analysis = ConfigAnalysis(
        valid=not errors,
        protocol=protocol,
        protocol_label=PROTOCOL_LABELS[protocol],
        errors=errors,
        warnings=warnings,
        address=addresses,
        dns=dns,
        mtu=mtu,
        peer_count=len(peer_groups),
        endpoints=endpoints,
        allowed_ips=allowed_ips,
        full_tunnel=full_tunnel,
        has_ipv6=has_ipv6,
        persistent_keepalive=persistent_keepalive,
    )
    return analysis.to_dict()
