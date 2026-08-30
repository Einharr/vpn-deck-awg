"""Extended ConfigManager with Amnezia vpn:// and JSON source support."""

from __future__ import annotations

import os
from typing import Dict

from .config_manager import ConfigManager as BaseConfigManager, MAX_CONFIG_BYTES
from .config_source import normalize_config_source


class ConfigManager(BaseConfigManager):
    def _load_source(self, path: str) -> Dict:
        if not path or not os.path.isfile(path):
            return {"success": False, "error": "File not found", "format": "unknown"}
        try:
            if os.path.getsize(path) > MAX_CONFIG_BYTES:
                return {"success": False, "error": "Config file is too large", "format": "unknown"}
            with open(path, "r", encoding="utf-8-sig") as handle:
                raw = handle.read(MAX_CONFIG_BYTES + 1)
        except (OSError, UnicodeError) as exc:
            return {"success": False, "error": f"Cannot read config: {exc}", "format": "unknown"}

        if len(raw.encode("utf-8")) > MAX_CONFIG_BYTES:
            return {"success": False, "error": "Config file is too large", "format": "unknown"}
        return normalize_config_source(raw)

    def inspect_file(self, path: str) -> Dict:
        source = self._load_source(path)
        if not source.get("success"):
            # Always return the same metadata shape as validate_config(). The
            # beta.3 UI renders this object even for rejected files; returning
            # a partial dict made protocolTone(undefined) crash Steam's React
            # tree before the actual validation error could be shown.
            result = self.validate_config("")
            result["valid"] = False
            result["errors"] = [source.get("error") or "Unsupported config source"]
            result["warnings"] = []
            result["source_format"] = source.get("format", "unknown")
            result["suggested_name"] = self.sanitize_name(os.path.basename(path or "vpn"))
            return result

        result = self.validate_config(source["content"])
        result["source_format"] = source.get("format", "conf")
        result["suggested_name"] = self.sanitize_name(os.path.basename(path))
        source_warnings = source.get("warnings") or []
        if source_warnings:
            result["warnings"] = list(result.get("warnings", [])) + list(source_warnings)
        return result

    def import_file(self, name: str, path: str, overwrite: bool = False) -> Dict:
        source = self._load_source(path)
        if not source.get("success"):
            return {
                "success": False,
                "error": source.get("error") or "Unsupported config source",
                "analysis": self.inspect_file(path),
            }

        analysis = self.validate_config(source["content"])
        if not analysis.get("valid"):
            return {
                "success": False,
                "error": "; ".join(analysis.get("errors", [])) or "Invalid config",
                "analysis": analysis,
            }

        result = self.write_config(name, source["content"], overwrite=overwrite)
        if result.get("analysis") is not None:
            result["analysis"]["source_format"] = source.get("format", "conf")
            source_warnings = source.get("warnings") or []
            if source_warnings:
                result["analysis"]["warnings"] = list(result["analysis"].get("warnings", [])) + list(source_warnings)
        return result
