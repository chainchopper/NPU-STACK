import unittest
from unittest.mock import patch

from backend.services.edge_discovery import (
    _classify_network_endpoint,
    _parse_known_host_tokens,
    _parse_probe_target,
    _parse_http_probe,
)


class EdgeDiscoveryTests(unittest.TestCase):
    def test_parse_http_probe_extracts_headers_and_title(self):
        parsed = _parse_http_probe(
            "HTTP/1.1 200 OK\r\n"
            "Server: ESPHome Dashboard\r\n"
            "Location: /login\r\n\r\n"
            "<html><head><title>LuckFox Pico Dashboard</title></head><body>RV1106 edge node</body></html>"
        )

        self.assertEqual(parsed["server_header"], "ESPHome Dashboard")
        self.assertEqual(parsed["location"], "/login")
        self.assertEqual(parsed["page_title"], "LuckFox Pico Dashboard")
        self.assertIn("RV1106 edge node", parsed["body_preview"])

    def test_classify_network_endpoint_detects_luckfox_signals(self):
        detected = _classify_network_endpoint(
            hostname="",
            server_header="lighttpd/1.4",
            page_title="LuckFox Pico Controller",
            body_preview="RV1106 Buildroot edge camera",
            ssh_banner="SSH-2.0-dropbear",
        )

        self.assertEqual(detected["family"], "rockchip")
        self.assertEqual(detected["chip"], "LuckFox Pico")
        self.assertTrue(detected["has_npu"])

    def test_classify_network_endpoint_detects_esphome_esp32(self):
        detected = _classify_network_endpoint(
            hostname="living-room-esphome",
            server_header="ESPHome WebServer",
            page_title="ESPHome",
            body_preview="ESP32-S3 relay controller",
            ssh_banner="",
        )

        self.assertEqual(detected["family"], "esp32-s3")
        self.assertEqual(detected["chip"], "ESP32-S3")
        self.assertFalse(detected["has_npu"])

    def test_parse_known_host_tokens_merges_user_input_and_registry(self):
        registry = {
            "devices": {
                "net-1": {"connection": "wifi", "paired": True, "ip": "192.168.1.20", "host": "luckfox.local", "status": "reachable"},
                "net-2": {"connection": "wifi", "paired": False, "ip": "192.168.1.21", "host": "esphome.local", "status": "reachable"},
            }
        }

        with patch('backend.services.edge_discovery.load_registry', return_value=registry):
            tokens = _parse_known_host_tokens('192.168.1.20, 192.168.1.50; tasmota.local')

        self.assertCountEqual(tokens, ['192.168.1.20', '192.168.1.50', 'tasmota.local', 'luckfox.local', '192.168.1.21', 'esphome.local'])

    def test_parse_probe_target_extracts_scheme_host_and_port(self):
        self.assertEqual(_parse_probe_target('https://luckfox.local:8443'), ('luckfox.local', 8443, 'https'))
        self.assertEqual(_parse_probe_target('192.168.1.44'), ('192.168.1.44', None, None))


if __name__ == '__main__':
    unittest.main()
