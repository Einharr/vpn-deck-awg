import base64
import json
import os
import struct
import sys
import unittest
import types
import zlib

if "decky" not in sys.modules:
    sys.modules["decky"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None),
        DECKY_PLUGIN_LOG_DIR="/tmp",
        DECKY_PLUGIN_SETTINGS_DIR="/tmp",
        DECKY_USER_HOME="/tmp",
    )
decky = sys.modules["decky"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "py_modules"))

from vpn_deck.config_source import normalize_config_source
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


def amnezia_vpn_link() -> str:
    # Mirrors Qt qCompress: four-byte big-endian size followed by zlib data.
    last_config = {
        "config": config("Jc = 4\nJmin = 20\nJmax = 80\nS3 = 22\nS4 = 24\n"),
        "header_protection_key": KEY_B,
        "content_padding_addition": "16-64",
        "rekey_after_time": "120-180",
        "rekey_timeout": "4-6",
        "reject_after_time": "170-190",
        "keepalive_timeout": "20-30",
        "max_handshake_attempts": "6-8",
    }
    root = {
        "containers": [{
            "container": "amnezia-awg",
            "awg": {"last_config": json.dumps(last_config)},
        }],
        "defaultContainer": "amnezia-awg",
    }
    raw = json.dumps(root).encode("utf-8")
    qcompressed = struct.pack(">I", len(raw)) + zlib.compress(raw, 8)
    encoded = base64.urlsafe_b64encode(qcompressed).decode("ascii").rstrip("=")
    return "vpn://" + encoded


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

    def test_plain_conf_source_is_unchanged(self):
        source = normalize_config_source(config())
        self.assertTrue(source["success"])
        self.assertEqual(source["format"], "conf")
        self.assertEqual(detect_protocol(source["content"]), "wireguard")

    def test_amnezia_vpn_link_restores_awg3_fields(self):
        source = normalize_config_source(amnezia_vpn_link())
        self.assertTrue(source["success"])
        self.assertEqual(source["format"], "amnezia-vpn-link")
        self.assertIn("HeaderProtectionKey = " + KEY_B, source["content"])
        self.assertIn("ContentPaddingAddition = 16-64", source["content"])
        self.assertIn("MaxHandshakeAttempts = 6-8", source["content"])
        analysis = analyse_config(source["content"])
        self.assertTrue(analysis["valid"])
        self.assertEqual(analysis["protocol"], "awg-3.0")
        self.assertEqual(analysis["peer_count"], 1)
        self.assertEqual(analysis["endpoints"], ["vpn.example.org:51820"])

    def test_amnezia_json_string_last_config(self):
        root = {
            "awg": {
                "last_config": json.dumps({
                    "config": config("Jc = 3\nJmin = 20\nJmax = 60\n"),
                    "HeaderProtectionKey": KEY_B,
                })
            }
        }
        source = normalize_config_source(json.dumps(root))
        self.assertTrue(source["success"])
        self.assertEqual(detect_protocol(source["content"]), "awg-3.0")


if __name__ == "__main__":
    unittest.main()
