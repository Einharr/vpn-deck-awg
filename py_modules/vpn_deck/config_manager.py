"""Persistent VPN profile storage, migration and validation."""

from __future__ import annotations

import os
import re
import shutil
from typing import Dict, List, Optional

import decky

from .protocol import analyse_config


MAX_CONFIG_BYTES = 256 * 1024
MAX_PROFILE_NAME = 12  # vd- prefix + name must fit IFNAMSIZ (15 chars)
VALID_INTERFACE_CHARS = re.compile(r"[^a-zA-Z0-9_=+.-]+")


class ConfigManager:
    def __init__(self) -> None:
        self.config_dir = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "configs")
        self.system_config_dir = "/etc/amnezia/amneziawg"
        self.config_prefix = "vd-"
        os.makedirs(self.config_dir, mode=0o700, exist_ok=True)
        self._migrate_legacy_configs()

    def _legacy_dirs(self) -> List[str]:
        candidates: List[str] = []
        homes = [getattr(decky, "DECKY_USER_HOME", "/home/deck")]
        runtime_home = getattr(decky, "HOME", "")
        if runtime_home and runtime_home not in homes:
            homes.append(runtime_home)
        for home in homes:
            path = os.path.join(home, ".local", "share", "vpn-deck", "configs")
            if path not in candidates:
                candidates.append(path)
        return candidates

    def _migrate_legacy_configs(self) -> None:
        for legacy_dir in self._legacy_dirs():
            if not os.path.isdir(legacy_dir) or os.path.abspath(legacy_dir) == os.path.abspath(self.config_dir):
                continue
            try:
                for filename in os.listdir(legacy_dir):
                    if not filename.endswith(".conf"):
                        continue
                    src = os.path.join(legacy_dir, filename)
                    dst = os.path.join(self.config_dir, filename)
                    if os.path.isfile(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        os.chmod(dst, 0o600)
                        decky.logger.info(f"Migrated legacy VPN config: {filename}")
            except OSError as exc:
                decky.logger.warning(f"Legacy config migration failed for {legacy_dir}: {exc}")

    def sanitize_name(self, name: str) -> str:
        raw = os.path.basename((name or "").strip())
        if raw.lower().endswith(".conf"):
            raw = raw[:-5]
        sanitized = VALID_INTERFACE_CHARS.sub("-", raw).strip("-.").lower()
        sanitized = re.sub(r"-+", "-", sanitized)
        if not sanitized:
            sanitized = "vpn"
        return sanitized[:MAX_PROFILE_NAME]

    # Compatibility with the original plugin/tests.
    def _sanitize_name(self, name: str) -> str:
        return self.sanitize_name(name)

    def get_interface_name(self, name: str) -> str:
        return f"{self.config_prefix}{self.sanitize_name(name)}"

    def _paths(self, name: str) -> Dict[str, str]:
        clean = self.sanitize_name(name)
        interface = self.get_interface_name(clean)
        return {
            "name": clean,
            "interface": interface,
            "local": os.path.join(self.config_dir, f"{clean}.conf"),
            "system": os.path.join(self.system_config_dir, f"{interface}.conf"),
        }

    @staticmethod
    def validate_config(content: str) -> Dict:
        return analyse_config(content)

    def inspect_file(self, path: str) -> Dict:
        if not path or not os.path.isfile(path):
            return {"valid": False, "errors": ["File not found"], "warnings": []}
        if os.path.getsize(path) > MAX_CONFIG_BYTES:
            return {"valid": False, "errors": ["Config file is too large"], "warnings": []}
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                content = handle.read()
        except (OSError, UnicodeError) as exc:
            return {"valid": False, "errors": [f"Cannot read config: {exc}"], "warnings": []}
        result = self.validate_config(content)
        result["suggested_name"] = self.sanitize_name(os.path.basename(path))
        return result

    def _ensure_symlink(self, local_path: str, system_path: str) -> Dict:
        try:
            os.makedirs(os.path.dirname(system_path), mode=0o755, exist_ok=True)
            if os.path.islink(system_path):
                try:
                    if os.path.realpath(system_path) == os.path.realpath(local_path):
                        return {"ok": True, "action": "none", "error": None}
                except OSError:
                    pass
                os.unlink(system_path)
                action = "replaced"
            elif os.path.lexists(system_path):
                # Never overwrite a real system config that the plugin does not own.
                return {"ok": False, "action": "conflict", "error": "System config path is occupied"}
            else:
                action = "created"

            os.symlink(local_path, system_path)
            return {"ok": True, "action": action, "error": None}
        except OSError as exc:
            return {"ok": False, "action": "error", "error": str(exc)}

    def write_config(self, name: str, content: str, overwrite: bool = False) -> Dict:
        analysis = self.validate_config(content)
        if not analysis.get("valid"):
            return {
                "success": False,
                "error": "; ".join(analysis.get("errors", [])) or "Invalid config",
                "analysis": analysis,
            }

        paths = self._paths(name)
        if os.path.exists(paths["local"]) and not overwrite:
            return {
                "success": False,
                "error": "A profile with this name already exists",
                "exists": True,
                "config_name": paths["name"],
                "analysis": analysis,
            }

        tmp = paths["local"] + ".tmp"
        previous: Optional[bytes] = None
        if os.path.exists(paths["local"]):
            try:
                with open(paths["local"], "rb") as handle:
                    previous = handle.read()
            except OSError:
                previous = None
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                if content and not content.endswith("\n"):
                    handle.write("\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, paths["local"])
            link = self._ensure_symlink(paths["local"], paths["system"])
            if not link["ok"]:
                if previous is None:
                    try:
                        os.unlink(paths["local"])
                    except OSError:
                        pass
                else:
                    with open(paths["local"], "wb") as handle:
                        handle.write(previous)
                    os.chmod(paths["local"], 0o600)
                return {
                    "success": False,
                    "error": link["error"],
                    "config_name": paths["name"],
                    "analysis": analysis,
                }
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return {"success": False, "error": str(exc), "analysis": analysis}

        return {
            "success": True,
            "error": None,
            "config_name": paths["name"],
            "interface_name": paths["interface"],
            "analysis": analysis,
        }

    def import_file(self, name: str, path: str, overwrite: bool = False) -> Dict:
        inspected = self.inspect_file(path)
        if not inspected.get("valid"):
            return {"success": False, "error": "; ".join(inspected.get("errors", [])), "analysis": inspected}
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                content = handle.read()
        except (OSError, UnicodeError) as exc:
            return {"success": False, "error": str(exc), "analysis": inspected}
        return self.write_config(name, content, overwrite=overwrite)

    def _read_analysis(self, path: str) -> Dict:
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                content = handle.read(MAX_CONFIG_BYTES + 1)
            if len(content.encode("utf-8")) > MAX_CONFIG_BYTES:
                raise ValueError("Config too large")
            return self.validate_config(content)
        except Exception as exc:
            return {
                "valid": False,
                "protocol": "unknown",
                "protocol_label": "Unknown",
                "errors": [str(exc)],
                "warnings": [],
                "address": [],
                "dns": [],
                "peer_count": 0,
                "endpoints": [],
                "allowed_ips": [],
                "full_tunnel": False,
                "has_ipv6": False,
                "persistent_keepalive": False,
                "mtu": None,
            }

    def _profile(self, name: str, path: str, managed_by: str, system_path: str) -> Dict:
        clean = self.sanitize_name(name)
        interface = self.get_interface_name(clean) if managed_by == "vpn-deck" else clean
        analysis = self._read_analysis(path)
        endpoint = analysis.get("endpoints", [None])[0] if analysis.get("endpoints") else None
        return {
            "name": clean,
            "interface": interface,
            "path": path,
            "system_path": system_path,
            "managed_by": managed_by,
            "is_symlink": os.path.islink(system_path) if system_path else False,
            "protocol": analysis.get("protocol", "unknown"),
            "protocol_label": analysis.get("protocol_label", "Unknown"),
            "valid": bool(analysis.get("valid")),
            "warnings": analysis.get("warnings", []),
            "errors": analysis.get("errors", []),
            "address": analysis.get("address", []),
            "dns": analysis.get("dns", []),
            "peer_count": analysis.get("peer_count", 0),
            "endpoint": endpoint,
            "endpoints": analysis.get("endpoints", []),
            "allowed_ips": analysis.get("allowed_ips", []),
            "full_tunnel": bool(analysis.get("full_tunnel")),
            "has_ipv6": bool(analysis.get("has_ipv6")),
            "persistent_keepalive": bool(analysis.get("persistent_keepalive")),
            "mtu": analysis.get("mtu"),
        }

    async def scan_existing_configs(self) -> Dict[str, List[Dict]]:
        result: Dict[str, List[Dict]] = {"managed": [], "existing": []}

        if os.path.isdir(self.config_dir):
            for filename in sorted(os.listdir(self.config_dir)):
                if not filename.endswith(".conf"):
                    continue
                name = filename[:-5]
                paths = self._paths(name)
                result["managed"].append(
                    self._profile(name, paths["local"], "vpn-deck", paths["system"])
                )

        if os.path.isdir(self.system_config_dir):
            for filename in sorted(os.listdir(self.system_config_dir)):
                if not filename.endswith(".conf") or filename.startswith(self.config_prefix):
                    continue
                path = os.path.join(self.system_config_dir, filename)
                if os.path.isfile(path):
                    result["existing"].append(
                        self._profile(filename[:-5], path, "user", path)
                    )

        return result

    async def list_all_configs(self) -> List[Dict]:
        scanned = await self.scan_existing_configs()
        return scanned["managed"] + scanned["existing"]

    async def get_config_content(self, name: str) -> Optional[str]:
        path = self._paths(name)["local"]
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return handle.read()
        except OSError:
            return None

    async def repair_symlinks(self) -> Dict:
        scanned = await self.scan_existing_configs()
        results = []
        for profile in scanned["managed"]:
            repair = self._ensure_symlink(profile["path"], profile["system_path"])
            results.append({
                "name": profile["name"],
                "interface": profile["interface"],
                "ok": repair["ok"],
                "action": repair["action"],
                "error": repair["error"],
            })
        repaired = sum(1 for item in results if item["ok"] and item["action"] in {"created", "replaced"})
        return {"total": len(results), "repaired": repaired, "results": results}

    async def delete_config(self, name: str) -> Dict:
        paths = self._paths(name)
        if not os.path.exists(paths["local"]):
            return {"success": False, "config_name": paths["name"], "error": "Profile not found"}
        try:
            os.unlink(paths["local"])
            if os.path.islink(paths["system"]):
                os.unlink(paths["system"])
            return {"success": True, "config_name": paths["name"], "error": None}
        except OSError as exc:
            return {"success": False, "config_name": paths["name"], "error": str(exc)}
