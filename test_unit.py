import asyncio
import os
import shutil
import sys
import tempfile
import unittest
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "py_modules"))

if "decky" not in sys.modules:
    sys.modules["decky"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None),
        DECKY_PLUGIN_LOG_DIR="/tmp",
        DECKY_PLUGIN_SETTINGS_DIR="/tmp",
        DECKY_USER_HOME="/tmp",
    )
decky = sys.modules["decky"]
from vpn_deck import ConfigManager

KEY_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
KEY_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
CONFIG = f"""[Interface]
PrivateKey = {KEY_A}
Address = 10.8.0.2/32
Jc = 4
Jmin = 20
Jmax = 80
S3 = 32
S4 = 64

[Peer]
PublicKey = {KEY_B}
Endpoint = vpn.example.org:51820
AllowedIPs = 0.0.0.0/0
"""


class ConfigManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="vpn-deck-awg-")
        decky.DECKY_PLUGIN_SETTINGS_DIR = os.path.join(self.temp, "settings")
        decky.DECKY_USER_HOME = os.path.join(self.temp, "home")
        self.cm = ConfigManager()
        self.cm.system_config_dir = os.path.join(self.temp, "system")
        os.makedirs(self.cm.system_config_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_name_sanitization_and_limit(self):
        self.assertEqual(self.cm.sanitize_name("My VPN.conf"), "my-vpn")
        self.assertEqual(len(self.cm.sanitize_name("abcdefghijklmnop")), 12)

    def test_import_and_metadata(self):
        result = self.cm.write_config("work", CONFIG)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["analysis"]["protocol"], "awg-2.0")
        self.assertTrue(os.path.islink(os.path.join(self.cm.system_config_dir, "vd-work.conf")))

        profiles = asyncio.run(self.cm.list_all_configs())
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["protocol_label"], "AmneziaWG 2.0")
        self.assertEqual(profiles[0]["endpoint"], "vpn.example.org:51820")

    def test_duplicate_requires_explicit_overwrite(self):
        self.assertTrue(self.cm.write_config("work", CONFIG)["success"])
        duplicate = self.cm.write_config("work", CONFIG)
        self.assertFalse(duplicate["success"])
        self.assertTrue(duplicate["exists"])
        self.assertTrue(self.cm.write_config("work", CONFIG, overwrite=True)["success"])

    def test_invalid_rejected(self):
        result = self.cm.write_config("bad", "[Interface]\nAddress=10.0.0.1/32\n")
        self.assertFalse(result["success"])
        self.assertFalse(os.path.exists(os.path.join(self.cm.config_dir, "bad.conf")))

    def test_delete(self):
        self.assertTrue(self.cm.write_config("work", CONFIG)["success"])
        result = asyncio.run(self.cm.delete_config("work"))
        self.assertTrue(result["success"])
        self.assertFalse(os.path.exists(os.path.join(self.cm.config_dir, "work.conf")))


if __name__ == "__main__":
    unittest.main()
