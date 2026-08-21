import os
import sys
import unittest
import types

if "decky" not in sys.modules:
    sys.modules["decky"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None),
        DECKY_PLUGIN_LOG_DIR="/tmp",
        DECKY_PLUGIN_SETTINGS_DIR="/tmp",
        DECKY_USER_HOME="/tmp",
    )
decky = sys.modules["decky"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "py_modules"))

from vpn_deck.protocol import analyse_config, detect_protocol

KEY_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
KEY_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="


def config(extra: str = "") -> str:
    return f"""[Interface]
PrivateKey = {KEY_A}
Address = 10.10.0.2/32
{extra}
[Peer]
PublicKey = {KEY_B}
Endpoint = vpn.example.org:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""


class ProtocolTests(unittest.TestCase):
    def test_wireguard(self):
        self.assertEqual(detect_protocol(config()), "wireguard")

    def test_awg_1(self):
        text = config("Jc = 4\nJmin = 20\nJmax = 80\nS1 = 12\nS2 = 24\nH1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n")
        self.assertEqual(detect_protocol(text), "awg-1.0")

    def test_awg_15(self):
        text = config("Jc = 4\nJmin = 20\nJmax = 80\nI1 = <b 0x01>\n")
        self.assertEqual(detect_protocol(text), "awg-1.5")

    def test_awg_2(self):
        text = config("Jc = 4\nJmin = 20\nJmax = 80\nS3 = 32\nS4 = 64\nI1 = <b 0x01>\nI2 = <b 0x02>\n")
        self.assertEqual(detect_protocol(text), "awg-2.0")

    def test_awg_3(self):
        text = config("Jc = 4\nJmin = 20\nJmax = 80\nHeaderProtectionKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\nContentPaddingAddition = 0-64\nRekeyAfterTime = 120-180\n")
        self.assertEqual(detect_protocol(text), "awg-3.0")

    def test_analysis_has_no_secrets(self):
        result = analyse_config(config())
        rendered = repr(result)
        self.assertTrue(result["valid"])
        self.assertTrue(result["full_tunnel"])
        self.assertNotIn(KEY_A, rendered)
        self.assertNotIn(KEY_B, rendered)

    def test_invalid_config(self):
        result = analyse_config("[Interface]\nAddress=10.0.0.2/32\n")
        self.assertFalse(result["valid"])
        self.assertTrue(any("PrivateKey" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
