"""Emulator shim support for the on-device provisioning modules (IMPROV BLE + ESP-NOW).

Verifies `improv_ble` and `espnow_pair` run unchanged inside the emulator shim,
so the onboarding flow (SoftAP QR + IMPROV HTTP/BLE + ESP-NOW beacon) can be
exercised in the Device Playground without hardware.
"""
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from backend.emulator import shim

_FW = os.path.join(REPO, "firmware", "nirvana-os")
if _FW not in sys.path:
    sys.path.insert(0, _FW)


class TestEmulatorProvisioning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shim.install()

    def test_improv_ble_send_wifi_rpc(self):
        import improv_ble

        captured = {}

        def on_creds(ssid, pwd):
            captured["ssid"] = ssid
            captured["pwd"] = pwd

        ble = improv_ble.ImprovBLE(on_credentials=on_creds)
        ble.advertise()
        self.assertIsNotNone(ble._ble._adv)
        self.assertEqual(len(ble._ble._adv), 31, "IMPROV adv payload must fit in 31 bytes")

        ssid, pwd = b"MyWiFi", b"secret123"
        data = bytes([len(ssid)]) + ssid + bytes([len(pwd)]) + pwd
        pkt = bytes([0x01, len(data)]) + data
        pkt += bytes([sum(pkt) & 0xFF])  # checksum

        self.assertTrue(shim.inject_ble_rpc(pkt))
        self.assertEqual(captured, {"ssid": "MyWiFi", "pwd": "secret123"})
        self.assertEqual(ble._state, improv_ble.ST_PROVISIONING)

    def test_espnow_pair_offer(self):
        import espnow_pair

        captured = {}

        def on_pair(ssid, pwd, extra):
            captured.update(ssid=ssid, pwd=pwd, extra=extra)

        p = espnow_pair.EspNowPair(on_pair=on_pair)
        p.start()
        self.assertEqual(p._e.peer_count()[0], 1, "broadcast peer should be added")

        offer = ("NPUPAIR1|" + json.dumps({
            "ssid": "HomeNet", "pass": "pw123",
            "backend": "http://192.168.1.232:8010",
        })).encode("utf-8")
        shim.inject_espnow(b"\xff" * 6, offer)

        res = p.poll()
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "HomeNet")
        self.assertEqual(res[1], "pw123")
        self.assertEqual(captured["ssid"], "HomeNet")


if __name__ == "__main__":
    unittest.main()
