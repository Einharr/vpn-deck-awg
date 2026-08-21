"""Persistent plugin settings."""

from __future__ import annotations

import json
import os
from typing import Dict

import decky


DEFAULT_SETTINGS = {
    "exclusive_mode": True,
    "auto_repair": True,
    "last_connected": None,
}


class SettingsManager:
    def __init__(self) -> None:
        self.path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)

    def get(self) -> Dict:
        data = dict(DEFAULT_SETTINGS)
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                data.update({k: stored[k] for k in DEFAULT_SETTINGS if k in stored})
        except FileNotFoundError:
            pass
        except Exception as exc:
            decky.logger.warning(f"Failed to read settings: {exc}")
        return data

    def update(self, changes: Dict) -> Dict:
        current = self.get()
        if "exclusive_mode" in changes:
            current["exclusive_mode"] = bool(changes["exclusive_mode"])
        if "auto_repair" in changes:
            current["auto_repair"] = bool(changes["auto_repair"])
        if "last_connected" in changes:
            value = changes["last_connected"]
            current["last_connected"] = str(value) if value else None

        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(current, handle, indent=2, sort_keys=True)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.path)
        return current
