import asyncio
import os
import shutil
import sys
import tempfile
import unittest
import types
from unittest.mock import patch

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
from vpn_deck.transport import EndpointBypass
import vpn_deck.transport as transport_module

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


class EndpointBypassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="vpn-deck-route-")
        self.old_state_dir = transport_module.STATE_DIR
        transport_module.STATE_DIR = self.temp
        self.commands = []

        def fake_run(cmd, timeout=10, quiet=False):
            self.commands.append(list(cmd))
            if "route" in cmd and "get" in cmd:
                return 0, f"{cmd[-1]} via 192.168.1.1 dev wlan0 src 192.168.1.20", ""
            return 0, "", ""

        self.guard = EndpointBypass(fake_run, os.path.join(self.temp, "route.log"))

    def tearDown(self):
        transport_module.STATE_DIR = self.old_state_dir
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_hostname_endpoint_rule_is_installed_and_verified(self):
        with patch(
            "vpn_deck.transport.socket.getaddrinfo",
            return_value=[(2, 2, 17, "", ("203.0.113.10", 51820))],
        ):
            result = self.guard.install("vd-test", ["vpn.example.org:51820"])

        self.assertTrue(result["success"], result)
        self.assertEqual(result["resolved"][0]["cidr"], "203.0.113.10/32")
        self.assertIn(
            ["ip", "-4", "rule", "add", "pref", "9990", "to", "203.0.113.10/32", "lookup", "main"],
            self.commands,
        )
        verify = self.guard.verify("vd-test", result["resolved"])
        self.assertTrue(verify["success"], verify)

        self.guard.remove("vd-test")
        self.assertIn(
            ["ip", "-4", "rule", "del", "pref", "9990", "to", "203.0.113.10/32", "lookup", "main"],
            self.commands,
        )

    def test_policy_rule_wins_even_if_route_get_reports_tunnel(self):
        def fake_run(cmd, timeout=10, quiet=False):
            if cmd[-2:] == ["rule", "show"]:
                return 0, "9990: from all to 203.0.113.10 lookup main", ""
            if "route" in cmd and "get" in cmd:
                return 0, "203.0.113.10 dev vd-test table 51820 src 10.8.0.2", ""
            return 0, "", ""

        guard = EndpointBypass(fake_run, os.path.join(self.temp, "policy.log"))
        result = guard.verify(
            "vd-test",
            [{
                "source": "203.0.113.10:51820",
                "ip": "203.0.113.10",
                "proto": "-4",
                "cidr": "203.0.113.10/32",
            }],
        )
        self.assertTrue(result["success"], result)
        self.assertTrue(result["checks"][0]["direct_rule"])

    def test_ipv6_endpoint_parser(self):
        self.assertEqual(self.guard.split_endpoint("[2001:db8::1]:51820"), ("2001:db8::1", 51820))


if __name__ == "__main__":
    unittest.main()
