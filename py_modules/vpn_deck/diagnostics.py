"""Small, neutral connectivity probes for VPN troubleshooting."""

from __future__ import annotations

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import decky

from ._utils import clean_env


DEFAULT_TARGETS: List[Dict] = [
    {"name": "Internet", "kind": "ping", "host": "1.1.1.1"},
    {"name": "DNS", "kind": "dns", "host": "example.com"},
    {"name": "HTTPS", "kind": "http", "url": "https://example.com"},
]


class Diagnostics:
    def check(self, targets: Optional[List[Dict]] = None) -> List[Dict]:
        probes = targets if targets is not None else DEFAULT_TARGETS
        if not probes:
            return []
        with ThreadPoolExecutor(max_workers=min(len(probes), 4)) as pool:
            return list(pool.map(self._probe, probes))

    def _probe(self, target: Dict) -> Dict:
        kind = target.get("kind")
        name = target.get("name") or target.get("host") or target.get("url") or "?"
        if kind == "ping":
            return self._ping(name, str(target.get("host", "")))
        if kind == "dns":
            return self._dns(name, str(target.get("host", "")))
        if kind == "http":
            return self._http(name, str(target.get("url", "")))
        return {"name": name, "kind": kind or "unknown", "ok": False, "detail": "unknown probe", "target": "", "latency_ms": None}

    @staticmethod
    def _ping(name: str, host: str) -> Dict:
        try:
            result = subprocess.run(
                ["ping", "-c", "2", "-W", "2", "-n", host],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env=clean_env(),
            )
            ok = result.returncode == 0
            avg_ms = None
            if ok:
                match = re.search(r"min/avg/max/\S+\s*=\s*[\d.]+/([\d.]+)/", result.stdout)
                if match:
                    avg_ms = float(match.group(1))
            detail = f"{avg_ms:.1f} ms" if avg_ms is not None else (result.stderr.strip() or ("ok" if ok else "no response"))
            return {"name": name, "kind": "ping", "target": host, "ok": ok, "detail": detail, "latency_ms": avg_ms}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"name": name, "kind": "ping", "target": host, "ok": False, "detail": "unavailable", "latency_ms": None}

    @staticmethod
    def _dns(name: str, host: str) -> Dict:
        try:
            result = subprocess.run(
                ["getent", "ahostsv4", host],
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
                env=clean_env(),
            )
            ok = result.returncode == 0 and bool(result.stdout.strip())
            address = result.stdout.split()[0] if ok else None
            return {"name": name, "kind": "dns", "target": host, "ok": ok, "detail": address or "resolution failed", "latency_ms": None}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"name": name, "kind": "dns", "target": host, "ok": False, "detail": "resolver unavailable", "latency_ms": None}

    @staticmethod
    def _http(name: str, url: str) -> Dict:
        try:
            result = subprocess.run(
                ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{time_total}", "--max-time", "6", "-L", url],
                capture_output=True,
                text=True,
                timeout=9,
                check=False,
                env=clean_env(),
            )
            parts = result.stdout.strip().split()
            code = parts[0] if parts else "0"
            seconds = float(parts[1]) if len(parts) > 1 else None
            ok = code.startswith(("2", "3"))
            detail = f"HTTP {code}" + (f" · {seconds:.2f}s" if seconds is not None else "")
            return {"name": name, "kind": "http", "target": url, "ok": ok, "detail": detail, "latency_ms": seconds * 1000 if seconds is not None else None}
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            return {"name": name, "kind": "http", "target": url, "ok": False, "detail": "request failed", "latency_ms": None}
