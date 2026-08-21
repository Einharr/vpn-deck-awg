import asyncio
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "py_modules"))

if "decky" not in sys.modules:
    sys.modules["decky"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None),
        DECKY_PLUGIN_LOG_DIR="/tmp",
        DECKY_PLUGIN_SETTINGS_DIR="/tmp",
        DECKY_USER_HOME="/tmp",
        HOME="/tmp",
    )
decky = sys.modules["decky"]

from main import Plugin

KEY_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
KEY_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
CONFIG = f"""[Interface]
PrivateKey = {KEY_A}
Address = 10.5.0.2/32
Jc = 4
Jmin = 20
Jmax = 60
HeaderProtectionKey = {KEY_A}
ContentPaddingAddition = 0-32

[Peer]
PublicKey = {KEY_B}
Endpoint = vpn.example.org:443
AllowedIPs = 0.0.0.0/0
"""


class PluginSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="vpn-deck-plugin-")
        decky.DECKY_PLUGIN_SETTINGS_DIR = os.path.join(self.temp, "settings")
        decky.DECKY_PLUGIN_LOG_DIR = os.path.join(self.temp, "logs")
        decky.DECKY_USER_HOME = os.path.join(self.temp, "home")
        decky.HOME = os.path.join(self.temp, "root")
        os.makedirs(decky.DECKY_PLUGIN_LOG_DIR, exist_ok=True)
        self.plugin = Plugin()
        self.plugin.config_manager.system_config_dir = os.path.join(self.temp, "system")
        os.makedirs(self.plugin.config_manager.system_config_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_dashboard_shape(self):
        result = self.plugin.config_manager.write_config("home", CONFIG)
        self.assertTrue(result["success"], result)
        self.plugin.service_manager.active_interfaces = lambda: set()
        dashboard = asyncio.run(self.plugin.get_dashboard())
        self.assertTrue(dashboard["success"])
        self.assertEqual(dashboard["profiles"][0]["protocol"], "awg-3.0")
        self.assertFalse(dashboard["profiles"][0]["active"])

    def test_import_inspection(self):
        path = os.path.join(self.temp, "new.conf")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(CONFIG)
        inspected = asyncio.run(self.plugin.inspect_vpn_config(path))
        self.assertTrue(inspected["success"])
        self.assertEqual(inspected["analysis"]["protocol_label"], "AmneziaWG 3.0")

        imported = asyncio.run(self.plugin.import_vpn_config("new", path, False))
        self.assertTrue(imported["success"], imported)

    def test_settings(self):
        updated = asyncio.run(self.plugin.update_settings({"exclusive_mode": False}))
        self.assertTrue(updated["success"])
        self.assertFalse(updated["settings"]["exclusive_mode"])


if __name__ == "__main__":
    unittest.main()
