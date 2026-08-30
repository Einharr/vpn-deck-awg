"""Steam Deck specific service lifecycle checks layered over the upstream manager."""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional

import decky

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

    def _runtime_endpoints(self, interface: str) -> List[str]:
        """Return the concrete endpoints selected by awg after setconf.

        Hostnames may resolve to different addresses between the Python
        preflight and awg's own setconf. The runtime value is therefore the
        useful one for postflight diagnostics.
        """
        awg = self.binary_manager.get_binary_path("awg")
        if not awg:
            return []
        rc, stdout, _ = self._run([awg, "show", interface, "endpoints"], quiet=True)
        if rc != 0 or not stdout:
            return []

        endpoints: List[str] = []
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            endpoint = parts[-1].strip()
            if endpoint and endpoint != "(none)":
                endpoints.append(endpoint)
        return endpoints

    @staticmethod
    def _append_warning(message: str) -> None:
        decky.logger.warning(message)
        try:
            with open(AWG_QUICK_LOG, "a", encoding="utf-8") as handle:
                handle.write(f"[vpn-deck-awg] WARNING: {message}\n")
        except OSError:
            pass

    def _recover_incomplete_interface(self, interface: str) -> Dict:
        """Remove a half-created userspace interface left by a failed start.

        amneziawg-go creates the TUN/UAPI before awg-quick applies setconf. If
        awg-quick is interrupted at that point, the interface can survive with
        zero configured peers. Treat that state as incomplete rather than as
        an already-connected VPN.
        """
        rc_link, _, _ = self._run(["ip", "link", "show", "dev", interface], quiet=True)
        if rc_link != 0:
            return {"success": True, "recovered": False}

        if interface in self.active_interfaces():
            status = self.get_status(interface)
            if status.get("peers"):
                return {"success": True, "recovered": False, "already_active": True}

        self.endpoint_bypass.remove(interface)
        rc, _, error = self._run(["ip", "link", "delete", "dev", interface])
        if rc != 0:
            return {
                "success": False,
                "recovered": False,
                "error": error or f"Could not remove incomplete interface {interface}",
            }

        # Give the userspace daemon a moment to observe the deleted TUN and
        # close/remove its UAPI socket before starting the same name again.
        time.sleep(0.15)
        return {"success": True, "recovered": True}

    def start_interface(
        self,
        interface: str,
        endpoints: Optional[List[str]] = None,
        full_tunnel: Optional[bool] = None,
    ) -> Dict:
        if not self._safe_interface(interface):
            return {"success": False, "interface": interface, "method": None, "error": "Invalid interface name"}

        recovery = self._recover_incomplete_interface(interface)
        if not recovery.get("success"):
            return {
                "success": False,
                "interface": interface,
                "method": "stale-interface-cleanup",
                "error": recovery.get("error"),
            }
        if recovery.get("already_active"):
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
            # awg-quick normally cleans up itself, but a killed userspace
            # fallback can leave a TUN behind. Remove only an unconfigured one.
            self._recover_incomplete_interface(interface)
            return {
                "success": False,
                "interface": interface,
                "method": "awg-quick",
                "error": stderr or f"awg-quick up failed (rc={rc})",
                "transport_bypass": bypass,
            }

        if interface not in self.active_interfaces():
            self.endpoint_bypass.remove(interface)
            self._recover_incomplete_interface(interface)
            return {
                "success": False,
                "interface": interface,
                "method": "postflight",
                "error": "awg-quick returned RC 0, but the interface is not active",
                "transport_bypass": bypass,
            }

        # awg-quick has now resolved the actual peer endpoint and installed its
        # own destination policy rule. Prefer that concrete runtime endpoint for
        # diagnostics. Crucially, postflight diagnostics are NOT allowed to
        # tear down an interface that awg-quick successfully brought up.
        runtime_endpoints = self._runtime_endpoints(interface)
        runtime_resolved = self.endpoint_bypass.resolve(runtime_endpoints)
        checked = runtime_resolved or bypass.get("resolved", [])
        route_check = self.endpoint_bypass.verify(interface, checked)
        transport_warning = None
        if full_tunnel and not route_check.get("success"):
            transport_warning = route_check.get("error") or "Endpoint route verification was inconclusive"
            self._append_warning(
                f"Postflight route verification for {interface} was inconclusive; keeping the active tunnel: {transport_warning}"
            )

        return {
            "success": True,
            "interface": interface,
            "method": "awg-quick",
            "error": None,
            "transport_bypass": bypass,
            "transport_routes": route_check.get("checks", []),
            "transport_warning": transport_warning,
            "runtime_endpoints": runtime_endpoints,
            "recovered_stale_interface": bool(recovery.get("recovered")),
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
