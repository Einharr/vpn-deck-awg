"""Steam Deck specific service lifecycle checks layered over the upstream manager."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from .protocol import analyse_config
from .service_manager import AWG_QUICK_LOG, MANAGED_PREFIX, ServiceManager as BaseServiceManager
from .transport import EndpointBypass


class ServiceManager(BaseServiceManager):
    def __init__(self, binary_manager) -> None:
        super().__init__(binary_manager)
        self.endpoint_bypass = EndpointBypass(self._run, AWG_QUICK_LOG)

    @staticmethod
    def _routing_metadata(interface: str) -> Dict:
        path = os.path.join("/etc/amnezia/amneziawg", f"{interface}.conf")
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                analysis = analyse_config(handle.read())
        except (OSError, UnicodeError):
            return {"endpoints": [], "full_tunnel": False}
        return {
            "endpoints": list(analysis.get("endpoints") or []),
            "full_tunnel": bool(analysis.get("full_tunnel")),
        }

    def start_interface(
        self,
        interface: str,
        endpoints: Optional[List[str]] = None,
        full_tunnel: Optional[bool] = None,
    ) -> Dict:
        if not self._safe_interface(interface):
            return {"success": False, "interface": interface, "method": None, "error": "Invalid interface name"}
        if interface in self.active_interfaces():
            return {"success": True, "interface": interface, "method": "already-active", "error": None}

        awg_quick = self.binary_manager.get_binary_path("awg-quick")
        if not awg_quick:
            return {"success": False, "interface": interface, "method": None, "error": "awg-quick binary not found"}

        metadata = self._routing_metadata(interface)
        if endpoints is None:
            endpoints = metadata["endpoints"]
        if full_tunnel is None:
            full_tunnel = metadata["full_tunnel"]

        # Critical ordering: resolve and pin the transport endpoint while normal
        # Internet routing still exists, before awg-quick installs table 51820.
        bypass = self.endpoint_bypass.install(interface, endpoints)
        if full_tunnel and endpoints and not bypass.get("success"):
            return {
                "success": False,
                "interface": interface,
                "method": "preflight",
                "error": bypass.get("error"),
                "transport_bypass": bypass,
            }

        rc, _, stderr = self._run_logged([awg_quick, "up", interface])
        if rc != 0:
            self.endpoint_bypass.remove(interface)
            return {
                "success": False,
                "interface": interface,
                "method": "awg-quick",
                "error": stderr or f"awg-quick up failed (rc={rc})",
                "transport_bypass": bypass,
            }

        if interface not in self.active_interfaces():
            self.endpoint_bypass.remove(interface)
            return {
                "success": False,
                "interface": interface,
                "method": "postflight",
                "error": "awg-quick returned RC 0, but the interface is not active",
                "transport_bypass": bypass,
            }

        route_check = self.endpoint_bypass.verify(interface, bypass.get("resolved", []))
        if full_tunnel and not route_check.get("success"):
            self._run_logged([awg_quick, "down", interface])
            self.endpoint_bypass.remove(interface)
            return {
                "success": False,
                "interface": interface,
                "method": "postflight",
                "error": route_check.get("error"),
                "transport_bypass": bypass,
                "transport_routes": route_check.get("checks", []),
            }

        return {
            "success": True,
            "interface": interface,
            "method": "awg-quick",
            "error": None,
            "transport_bypass": bypass,
            "transport_routes": route_check.get("checks", []),
        }

    def stop_interface(self, interface: str) -> Dict:
        result = super().stop_interface(interface)
        # Cleanup even when the interface already vanished (reboot/crash/manual down).
        self.endpoint_bypass.remove(interface)
        return result

    def activate_interface(
        self,
        interface: str,
        exclusive: bool = True,
        endpoints: Optional[List[str]] = None,
        full_tunnel: Optional[bool] = None,
    ) -> Dict:
        if not self._safe_interface(interface):
            return {"success": False, "interface": interface, "error": "Invalid interface name", "stopped": []}

        stopped: List[str] = []
        failed: List[Dict] = []
        if exclusive:
            for other in sorted(self.active_interfaces()):
                if other == interface or not other.startswith(MANAGED_PREFIX):
                    continue
                result = self.stop_interface(other)
                if result["success"]:
                    stopped.append(other)
                else:
                    failed.append({"interface": other, "error": result.get("error")})
            if failed:
                return {
                    "success": False,
                    "interface": interface,
                    "error": "Could not stop an existing managed VPN",
                    "stopped": stopped,
                    "failed": failed,
                }

        result = self.start_interface(
            interface,
            endpoints=endpoints,
            full_tunnel=full_tunnel,
        )
        result["stopped"] = stopped
        return result
