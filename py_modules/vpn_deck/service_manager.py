"""Lifecycle and status management for WireGuard/AmneziaWG profiles."""

from __future__ import annotations

import os
import re
import signal
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Set

import decky

from ._utils import clean_env


MANAGED_PREFIX = "vd-"
START_STOP_TIMEOUT_SEC = 60
AWG_QUICK_LOG = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "awg-quick.log")
INTERFACE_RE = re.compile(r"^[a-zA-Z0-9_=+.-]{1,15}$")


class ServiceManager:
    def __init__(self, binary_manager) -> None:
        self.binary_manager = binary_manager

    @staticmethod
    def _safe_interface(interface: str) -> bool:
        return bool(INTERFACE_RE.fullmatch(interface or ""))

    def _run(self, cmd: List[str], timeout: int = 10, quiet: bool = False):
        log = decky.logger.debug if quiet else decky.logger.info
        log(f"Running: {' '.join(str(c) for c in cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=clean_env(),
                check=False,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return 124, "", f"timeout after {timeout}s"
        except FileNotFoundError:
            return 127, "", f"{cmd[0]}: command not found"

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen) -> None:
        """Terminate an awg-quick process and every child in its session."""
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            try:
                process.terminate()
            except OSError:
                return

        try:
            process.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            try:
                process.kill()
            except OSError:
                return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def _run_logged(self, cmd: List[str], timeout: int = START_STOP_TIMEOUT_SEC):
        cmd_str = " ".join(str(c) for c in cmd)
        process: Optional[subprocess.Popen] = None
        try:
            os.makedirs(os.path.dirname(AWG_QUICK_LOG), exist_ok=True)
            with open(AWG_QUICK_LOG, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n--- {datetime.now().isoformat()} | {cmd_str} ---\n")
                log_file.flush()
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=log_file,
                    text=True,
                    start_new_session=True,
                    env=clean_env(),
                )
                try:
                    returncode = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    log_file.write(f"\n--- TIMEOUT after {timeout}s; terminating process group ---\n")
                    log_file.flush()
                    self._terminate_process_group(process)
                    log_file.write("--- RC: 124 (timeout) ---\n")
                    log_file.flush()
                    return 124, "", f"timeout after {timeout}s; awg-quick process group terminated"

                log_file.write(f"--- RC: {returncode} ---\n")
                log_file.flush()

            error_tail = ""
            if returncode != 0:
                error_tail = self.get_log_tail(24)
            return returncode, "", error_tail
        except FileNotFoundError:
            return 127, "", f"{cmd[0]}: command not found"
        except OSError as exc:
            if process is not None and process.poll() is None:
                self._terminate_process_group(process)
            return 1, "", str(exc)

    def get_log_tail(self, lines: int = 60) -> str:
        try:
            with open(AWG_QUICK_LOG, "r", encoding="utf-8", errors="replace") as handle:
                return "".join(handle.readlines()[-max(1, min(lines, 200)):]).strip()
        except OSError:
            return ""

    def active_interfaces(self) -> Set[str]:
        awg = self.binary_manager.get_binary_path("awg")
        if not awg:
            return set()
        rc, stdout, _ = self._run([awg, "show", "interfaces"], quiet=True)
        return set(stdout.split()) if rc == 0 and stdout else set()

    def start_interface(self, interface: str) -> Dict:
        if not self._safe_interface(interface):
            return {"success": False, "interface": interface, "method": None, "error": "Invalid interface name"}
        if interface in self.active_interfaces():
            return {"success": True, "interface": interface, "method": "already-active", "error": None}

        awg_quick = self.binary_manager.get_binary_path("awg-quick")
        if not awg_quick:
            return {"success": False, "interface": interface, "method": None, "error": "awg-quick binary not found"}

        rc, _, stderr = self._run_logged([awg_quick, "up", interface])
        if rc == 0:
            return {"success": True, "interface": interface, "method": "awg-quick", "error": None}
        return {
            "success": False,
            "interface": interface,
            "method": "awg-quick",
            "error": stderr or f"awg-quick up failed (rc={rc})",
        }

    def stop_interface(self, interface: str) -> Dict:
        if not self._safe_interface(interface):
            return {"success": False, "interface": interface, "method": None, "error": "Invalid interface name"}
        if interface not in self.active_interfaces():
            return {"success": True, "interface": interface, "method": "already-inactive", "error": None}

        awg_quick = self.binary_manager.get_binary_path("awg-quick")
        if not awg_quick:
            return {"success": False, "interface": interface, "method": None, "error": "awg-quick binary not found"}
        rc, _, stderr = self._run_logged([awg_quick, "down", interface])
        if rc == 0:
            return {"success": True, "interface": interface, "method": "awg-quick", "error": None}
        return {
            "success": False,
            "interface": interface,
            "method": "awg-quick",
            "error": stderr or f"awg-quick down failed (rc={rc})",
        }

    def activate_interface(self, interface: str, exclusive: bool = True) -> Dict:
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

        result = self.start_interface(interface)
        result["stopped"] = stopped
        return result

    def _parse_awg_show(self, output: str) -> List[Dict]:
        peers: List[Dict] = []
        current: Optional[Dict] = None
        for line in output.splitlines():
            if line.startswith("peer:"):
                if current is not None:
                    peers.append(current)
                current = {
                    "public_key": line[len("peer:"):].strip(),
                    "endpoint": None,
                    "latest_handshake": None,
                    "transfer_rx": None,
                    "transfer_tx": None,
                }
                continue
            if current is None:
                continue
            stripped = line.strip()
            if stripped.startswith("endpoint:"):
                current["endpoint"] = stripped[len("endpoint:"):].strip()
            elif stripped.startswith("latest handshake:"):
                current["latest_handshake"] = stripped[len("latest handshake:"):].strip()
            elif stripped.startswith("transfer:"):
                parts = stripped[len("transfer:"):].strip().split(",")
                for part in parts:
                    text = part.strip()
                    if "received" in text:
                        current["transfer_rx"] = text.replace("received", "").strip()
                    elif "sent" in text:
                        current["transfer_tx"] = text.replace("sent", "").strip()
        if current is not None:
            peers.append(current)
        return peers

    def get_status(self, interface: str) -> Dict:
        active = interface in self.active_interfaces()
        result = {"interface": interface, "status": "active" if active else "inactive", "peers": []}
        if not active:
            return result
        awg = self.binary_manager.get_binary_path("awg")
        if not awg:
            result["status"] = "unknown"
            return result
        rc, stdout, stderr = self._run([awg, "show", interface], quiet=True)
        if rc != 0:
            result["status"] = "unknown"
            result["error"] = stderr or "awg show failed"
            return result
        result["peers"] = self._parse_awg_show(stdout)
        return result

    def get_all_statuses(self) -> List[Dict]:
        return [self.get_status(interface) for interface in sorted(self.active_interfaces())]

    def stop_all_interfaces(self, only_managed: bool = False) -> Dict:
        interfaces = sorted(self.active_interfaces())
        if only_managed:
            interfaces = [item for item in interfaces if item.startswith(MANAGED_PREFIX)]
        stopped: List[str] = []
        failed: List[Dict] = []
        for interface in interfaces:
            result = self.stop_interface(interface)
            if result["success"]:
                stopped.append(interface)
            else:
                failed.append({"interface": interface, "error": result.get("error")})
        return {"stopped": stopped, "failed": failed, "total": len(interfaces), "success": not failed}
