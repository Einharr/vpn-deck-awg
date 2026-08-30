"""Pre-tunnel transport routing for full-tunnel AmneziaWG/WireGuard profiles."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from typing import Callable, Dict, List, Optional

import decky


STATE_DIR = "/run/vpn-deck-awg"
RULE_PREF = 9990


class EndpointBypass:
    """Keep VPN peer endpoints on the physical/main routing table.

    This runs *before* awg-quick changes policy routing. It deliberately does
    not rely on ``awg show endpoints`` because on a userspace interface that
    information is only available after setconf, which is already late enough
    to race with full-tunnel routing changes.
    """

    def __init__(self, run: Callable, log_path: str) -> None:
        self._run = run
        self.log_path = log_path

    def _log(self, message: str) -> None:
        decky.logger.info(message)
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(f"[vpn-deck-awg] {message}\n")
        except OSError:
            pass

    @staticmethod
    def split_endpoint(endpoint: str):
        text = (endpoint or "").strip()
        if not text:
            return None, None
        if text.startswith("["):
            match = re.match(r"^\[([^\]]+)\]:(\d+)$", text)
            if not match:
                return None, None
            return match.group(1), int(match.group(2))
        host, sep, port = text.rpartition(":")
        if not sep or not host or not port.isdigit():
            return None, None
        return host, int(port)

    def resolve(self, endpoints: Optional[List[str]]) -> List[Dict]:
        resolved: List[Dict] = []
        seen = set()
        for endpoint in endpoints or []:
            host, port = self.split_endpoint(endpoint)
            if not host or port is None:
                continue

            try:
                addresses = [str(ipaddress.ip_address(host))]
            except ValueError:
                try:
                    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
                    addresses = [item[4][0] for item in infos]
                except OSError as exc:
                    self._log(f"Endpoint resolve failed for {host}: {exc}")
                    continue

            for address in addresses:
                try:
                    ip = ipaddress.ip_address(address.split("%", 1)[0])
                except ValueError:
                    continue
                key = (ip.version, str(ip))
                if key in seen:
                    continue
                seen.add(key)
                resolved.append({
                    "source": endpoint,
                    "ip": str(ip),
                    "proto": "-6" if ip.version == 6 else "-4",
                    "cidr": f"{ip}/{128 if ip.version == 6 else 32}",
                })
        return resolved

    @staticmethod
    def _state_file(interface: str) -> str:
        return os.path.join(STATE_DIR, f"{interface}.endpoint-rules")

    def remove(self, interface: str) -> None:
        path = self._state_file(interface)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                rows = [line.strip().split() for line in handle if line.strip()]
        except OSError:
            return

        for row in rows:
            if len(row) != 3:
                continue
            proto, pref, cidr = row
            self._run(
                ["ip", proto, "rule", "del", "pref", pref, "to", cidr, "lookup", "main"],
                quiet=True,
            )
        try:
            os.unlink(path)
        except OSError:
            pass
        self._log(f"Removed endpoint bypass for {interface}")

    def install(self, interface: str, endpoints: Optional[List[str]]) -> Dict:
        self.remove(interface)
        resolved = self.resolve(endpoints)
        if endpoints and not resolved:
            return {
                "success": False,
                "error": "Could not resolve the VPN endpoint before full-tunnel routing is enabled",
                "resolved": [],
            }
        if not resolved:
            return {"success": True, "error": None, "resolved": []}

        try:
            os.makedirs(STATE_DIR, mode=0o755, exist_ok=True)
        except OSError as exc:
            return {"success": False, "error": f"Cannot create route state: {exc}", "resolved": []}

        created: List[Dict] = []
        for index, item in enumerate(resolved):
            pref = str(RULE_PREF + index)
            rc, _, stderr = self._run(
                ["ip", item["proto"], "rule", "add", "pref", pref, "to", item["cidr"], "lookup", "main"],
                quiet=True,
            )
            if rc != 0:
                for old in created:
                    self._run(
                        ["ip", old["proto"], "rule", "del", "pref", old["pref"], "to", old["cidr"], "lookup", "main"],
                        quiet=True,
                    )
                return {
                    "success": False,
                    "error": stderr or f"Could not install transport bypass for {item['ip']}",
                    "resolved": [],
                }
            created.append({**item, "pref": pref})

        try:
            with open(self._state_file(interface), "w", encoding="utf-8") as handle:
                for item in created:
                    handle.write(f"{item['proto']} {item['pref']} {item['cidr']}\n")
        except OSError as exc:
            for item in created:
                self._run(
                    ["ip", item["proto"], "rule", "del", "pref", item["pref"], "to", item["cidr"], "lookup", "main"],
                    quiet=True,
                )
            return {"success": False, "error": f"Cannot persist route state: {exc}", "resolved": []}

        self._log(
            "Endpoint bypass installed BEFORE awg-quick: "
            + ", ".join(f"{item['cidr']} pref {item['pref']} -> main" for item in created)
        )
        return {"success": True, "error": None, "resolved": created}

    def verify(self, interface: str, resolved: List[Dict]) -> Dict:
        checks = []
        for item in resolved:
            rc, stdout, stderr = self._run(
                ["ip", item["proto"], "route", "get", item["ip"]],
                quiet=True,
            )
            route = stdout or stderr
            ok = rc == 0 and bool(stdout) and f"dev {interface}" not in stdout
            checks.append({"ip": item["ip"], "ok": ok, "route": route})

        failed = [item for item in checks if not item["ok"]]
        if failed:
            return {
                "success": False,
                "error": "VPN endpoint is routed into the tunnel: " + "; ".join(item["route"] for item in failed),
                "checks": checks,
            }
        return {"success": True, "error": None, "checks": checks}
