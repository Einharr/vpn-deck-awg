from __future__ import annotations

import functools
import time
import traceback as _traceback
from typing import Dict, List, Optional

import decky

from vpn_deck import BinaryManager, ConfigManager, Diagnostics, ServiceManager, SettingsManager


def _rpc(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as exc:
            trace = _traceback.format_exc()
            decky.logger.error(f"{func.__name__} exception: {trace}")
            if hasattr(self, "_add_error"):
                self._add_error(func.__name__, type(exc).__name__, str(exc), {"traceback": trace})
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    return wrapper


class Plugin:
    def __init__(self):
        self.errors: List[Dict] = []
        self.max_errors = 50
        self.binary_manager = BinaryManager()
        self.config_manager = ConfigManager()
        self.service_manager = ServiceManager(self.binary_manager)
        self.settings_manager = SettingsManager()
        self.diagnostics = Diagnostics()

    def _add_error(self, operation: str, error_type: str, message: str, details: Optional[Dict] = None):
        error = {
            "timestamp": time.time(),
            "operation": operation,
            "error_type": error_type,
            "message": message,
            "details": details or {},
        }
        self.errors.append(error)
        self.errors = self.errors[-self.max_errors:]
        decky.logger.error(f"VPN Deck AWG [{error_type}] {operation}: {message}")

    async def _main(self):
        decky.logger.info("VPN Deck AWG initialized")
        settings = self.settings_manager.get()
        if settings.get("auto_repair", True):
            try:
                repair = await self.config_manager.repair_symlinks()
                if repair["repaired"]:
                    decky.logger.info(f"Repaired {repair['repaired']} VPN config symlink(s)")
            except Exception as exc:
                self._add_error("startup-repair", type(exc).__name__, str(exc))

    async def _unload(self):
        decky.logger.info("VPN Deck AWG unloading")

    async def _uninstall(self):
        # Profiles are persistent user data. Never delete or disconnect them on
        # uninstall without explicit user action.
        decky.logger.info("VPN Deck AWG uninstalling; profiles retained")

    async def _migration(self):
        # ConfigManager performs a copy-only migration from legacy locations.
        decky.logger.info("VPN Deck AWG migration checked")

    async def _profiles_with_status(self) -> List[Dict]:
        scanned = await self.config_manager.scan_existing_configs()
        profiles = scanned["managed"]
        active = self.service_manager.active_interfaces()
        for profile in profiles:
            interface = profile["interface"]
            profile["active"] = interface in active
            profile["status"] = "active" if profile["active"] else "inactive"
            profile["peers"] = []
            if profile["active"]:
                status = self.service_manager.get_status(interface)
                profile["status"] = status.get("status", "unknown")
                profile["peers"] = status.get("peers", [])
        return profiles

    @_rpc
    async def get_dashboard(self) -> Dict:
        profiles = await self._profiles_with_status()
        settings = self.settings_manager.get()
        health = self.binary_manager.health()
        active_names = [p["name"] for p in profiles if p.get("active")]
        return {
            "success": True,
            "profiles": profiles,
            "active_count": len(active_names),
            "active_profiles": active_names,
            "settings": settings,
            "runtime": health,
            "error_count": len(self.errors),
            "last_error": self.errors[-1] if self.errors else None,
        }

    @_rpc
    async def inspect_vpn_config(self, path: str = "") -> Dict:
        if isinstance(path, dict):
            path = path.get("path", "")
        result = self.config_manager.inspect_file(path)
        return {"success": bool(result.get("valid")), "analysis": result, "error": None if result.get("valid") else "; ".join(result.get("errors", []))}

    @_rpc
    async def import_vpn_config(self, name: str, path: str = "", overwrite: bool = False) -> Dict:
        if isinstance(name, dict):
            payload = name
            name = payload.get("name", "")
            path = payload.get("path", path)
            overwrite = bool(payload.get("overwrite", overwrite))
        result = self.config_manager.import_file(name, path, overwrite=overwrite)
        if not result.get("success"):
            self._add_error("import", "ConfigError", result.get("error") or "Import failed", {"name": name})
        return result

    @_rpc
    async def vpn_activate_config(self, config_name: str, exclusive: Optional[bool] = None) -> Dict:
        if isinstance(config_name, dict):
            payload = config_name
            config_name = payload.get("config_name", "")
            if "exclusive" in payload:
                exclusive = bool(payload["exclusive"])
        if not config_name:
            return {"success": False, "error": "config_name is required", "interface": ""}

        settings = self.settings_manager.get()
        if exclusive is None:
            exclusive = bool(settings.get("exclusive_mode", True))
        interface = self.config_manager.get_interface_name(config_name)
        result = self.service_manager.activate_interface(interface, exclusive=bool(exclusive))
        if result.get("success"):
            self.settings_manager.update({"last_connected": self.config_manager.sanitize_name(config_name)})
        else:
            self._add_error("connect", "ServiceError", result.get("error") or "Connection failed", {"interface": interface})
        return result

    @_rpc
    async def vpn_start_config(self, config_name: str) -> Dict:
        # Backwards-compatible RPC used by older frontends.
        return await self.vpn_activate_config(config_name)

    @_rpc
    async def vpn_stop_config(self, config_name: str) -> Dict:
        if isinstance(config_name, dict):
            config_name = config_name.get("config_name", "")
        if not config_name:
            return {"success": False, "error": "config_name is required", "interface": ""}
        interface = self.config_manager.get_interface_name(config_name)
        result = self.service_manager.stop_interface(interface)
        if not result.get("success"):
            self._add_error("disconnect", "ServiceError", result.get("error") or "Disconnect failed", {"interface": interface})
        return result

    @_rpc
    async def vpn_stop_all(self, only_managed: bool = True) -> Dict:
        if isinstance(only_managed, dict):
            only_managed = bool(only_managed.get("only_managed", True))
        return self.service_manager.stop_all_interfaces(bool(only_managed))

    @_rpc
    async def list_configs_with_status(self) -> List[Dict]:
        return await self._profiles_with_status()

    @_rpc
    async def list_all_configs(self) -> List[Dict]:
        return await self.config_manager.list_all_configs()

    @_rpc
    async def scan_existing_configs(self) -> Dict:
        return await self.config_manager.scan_existing_configs()

    @_rpc
    async def delete_vpn_config(self, name: str) -> Dict:
        if isinstance(name, dict):
            name = name.get("name", "")
        if not name:
            return {"success": False, "error": "name is required", "config_name": None}
        await self.vpn_stop_config(name)
        return await self.config_manager.delete_config(name)

    @_rpc
    async def repair_symlinks(self) -> Dict:
        return await self.config_manager.repair_symlinks()

    @_rpc
    async def get_settings(self) -> Dict:
        return self.settings_manager.get()

    @_rpc
    async def update_settings(self, changes: Dict) -> Dict:
        if not isinstance(changes, dict):
            return {"success": False, "error": "settings payload must be an object"}
        return {"success": True, "settings": self.settings_manager.update(changes)}

    @_rpc
    async def get_binaries_info(self) -> Dict:
        return self.binary_manager.get_binaries_info()

    @_rpc
    async def check_binaries(self) -> Dict:
        return self.binary_manager.health()

    @_rpc
    async def diagnose_connectivity(self, targets: Optional[List[Dict]] = None) -> List[Dict]:
        if isinstance(targets, dict):
            targets = targets.get("targets")
        return self.diagnostics.check(targets)

    @_rpc
    async def get_service_log_tail(self, lines: int = 60) -> Dict:
        if isinstance(lines, dict):
            lines = int(lines.get("lines", 60))
        return {"success": True, "log": self.service_manager.get_log_tail(lines)}

    @_rpc
    async def get_errors(self) -> List[Dict]:
        return list(self.errors)

    @_rpc
    async def clear_errors(self) -> bool:
        self.errors = []
        return True

    @_rpc
    async def get_vpn_config(self, name: str) -> Optional[str]:
        # Kept for backwards compatibility. New UI does not expose secrets.
        return await self.config_manager.get_config_content(name)
