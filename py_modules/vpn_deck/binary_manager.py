"""Discovery and version reporting for bundled AmneziaWG binaries."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Dict, Optional

import decky


class BinaryManager:
    def __init__(self) -> None:
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.abspath(os.path.join(self.plugin_dir, "..", "..", "bin"))
        self.binary_names = ["amneziawg-go", "awg", "awg-quick"]
        self.binary_cache: Optional[Dict[str, Optional[str]]] = None
        self.metadata_path = os.path.join(self.bin_dir, "versions.json")

    def detect_binaries(self) -> Dict[str, Optional[str]]:
        if self.binary_cache is not None:
            return dict(self.binary_cache)

        binaries: Dict[str, Optional[str]] = {}
        for name in self.binary_names:
            path = os.path.join(self.bin_dir, name)
            binaries[name] = path if os.path.isfile(path) and os.access(path, os.X_OK) else None
            if binaries[name]:
                decky.logger.debug(f"Found {name}: {path}")
            else:
                decky.logger.error(f"Bundled binary missing or not executable: {path}")

        self.binary_cache = binaries
        return dict(binaries)

    def get_binary_path(self, name: str) -> Optional[str]:
        if name not in self.binary_names:
            return None
        return self.detect_binaries().get(name)

    def invalidate_cache(self) -> None:
        self.binary_cache = None

    @staticmethod
    def _extract_version(output: str) -> Optional[str]:
        match = re.search(r"v?(\d+\.\d+(?:\.\d+|\.\d{8})?)", output)
        return match.group(0) if match else (output.splitlines()[0].strip() if output else None)

    def _runtime_version(self, path: str) -> Optional[str]:
        for flag in ("--version", "-v"):
            try:
                result = subprocess.run(
                    [path, flag], capture_output=True, text=True, timeout=2, check=False
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            output = (result.stdout or result.stderr or "").strip()
            if result.returncode == 0 and output:
                return self._extract_version(output)
        return None

    def _build_metadata(self) -> Dict:
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get_binaries_info(self) -> Dict[str, Dict[str, Optional[str]]]:
        metadata = self._build_metadata()
        binaries = self.detect_binaries()
        result: Dict[str, Dict[str, Optional[str]]] = {}

        for name, path in binaries.items():
            pinned = metadata.get(name)
            # amneziawg-go 3.0.3 currently reports an old hard-coded version,
            # therefore reproducible build metadata is authoritative.
            runtime = self._runtime_version(path) if path else None
            result[name] = {
                "path": path,
                "version": str(pinned) if pinned else runtime,
                "runtime_version": runtime,
            }
        return result

    def health(self) -> Dict:
        binaries = self.detect_binaries()
        missing = [name for name, path in binaries.items() if not path]
        return {
            "ok": not missing,
            "missing": missing,
            "binaries": self.get_binaries_info(),
        }
