import asyncio
import unittest
from unittest.mock import patch

from backend.services.edge_discovery import (
    _build_capabilities,
    _classify_network_endpoint,
    _identify_by_heuristics,
    _parse_known_host_tokens,
    _parse_probe_target,
    _parse_http_probe,
    merge_into_registry,
    scan_network_neighbors,
    scan_windows_usb_pnp_devices,
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

    def test_quansheng_heuristic_beats_generic_ch340_detection(self):
        detected = _identify_by_heuristics('USB-SERIAL CH340', 'Quansheng', 'UV-K5 custom firmware')

        self.assertEqual(detected['family'], 'radio')
        self.assertEqual(detected['chip'], 'Quansheng UV-K5')

    def test_merge_into_registry_preserves_promoted_esp_identity(self):
        existing_registry = {
            'devices': {
                'usb-COM9': {
                    'id': 'usb-COM9',
                    'family': 'esp32-c3',
                    'chip': 'ESP32-C3 SuperMini',
                    'has_npu': False,
                    'flash_mb': 4,
                    'last_chip_detected_at': '2026-05-29T00:00:00+00:00',
                    'paired': True,
                }
            },
            'last_scan': None,
        }
        rediscovered = [{
            'id': 'usb-COM9',
            'family': 'uart-bridge',
            'chip': 'WCH CH340',
            'has_npu': False,
            'flash_mb': 0,
            'connection': 'usb',
            'status': 'detected',
            'discovered_at': '2026-05-29T00:00:01+00:00',
        }]

        with patch('backend.services.edge_discovery.load_registry', return_value=existing_registry), patch('backend.services.edge_discovery.save_registry'):
            merged = merge_into_registry(rediscovered)

        device = merged['devices']['usb-COM9']
        self.assertEqual(device['family'], 'esp32-c3')
        self.assertEqual(device['chip'], 'ESP32-C3 SuperMini')
        self.assertEqual(device['flash_mb'], 4)

    def test_merge_into_registry_keeps_low_confidence_network_hits(self):
        discovered = [{
            'id': 'net-192-168-1-50-80',
            'connection': 'wifi',
            'family': 'unknown',
            'chip': 'unknown',
            'description': '',
            'status': 'reachable',
            'discovered_at': '2026-05-29T00:00:01+00:00',
        }]

        with patch('backend.services.edge_discovery.load_registry', return_value={'devices': {}, 'last_scan': None}), patch('backend.services.edge_discovery.save_registry'):
            merged = merge_into_registry(discovered)

        self.assertIn('net-192-168-1-50-80', merged['devices'])

    def test_scan_windows_usb_pnp_devices_skips_serial_duplicate_and_keeps_rockusb(self):
        raw_usb = [
            {
                'Class': 'USB',
                'FriendlyName': 'USB Composite Device',
                'InstanceId': 'USB\\VID_239A&PID_8018\\75F8905050304D48502E3120FF010C31',
                'Manufacturer': 'Microsoft',
            },
            {
                'Class': 'Rockusb Device',
                'FriendlyName': 'Rockusb Device',
                'InstanceId': 'USB\\VID_2207&PID_110C\\B&2E5F6FA0&0&2',
                'Manufacturer': 'Rockchip',
            },
        ]
        serial_devices = [{
            'id': 'usb-COM12',
            'serial_number': '75F8905050304D48502E3120FF010C31',
            'vid': 0x239A,
            'pid': 0x8018,
            'hwid': 'USB VID:PID=239A:8018 SER=75F8905050304D48502E3120FF010C31',
        }]

        with patch('backend.services.edge_discovery._run_powershell_json', return_value=raw_usb), patch('backend.services.edge_discovery.platform.system', return_value='Windows'):
            devices = scan_windows_usb_pnp_devices(serial_devices=serial_devices)

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['family'], 'rockchip')
        self.assertIn('2207', devices[0]['instance_id'])

    def test_scan_network_neighbors_surfaces_visible_lan_entries(self):
        raw_neighbors = [
            {
                'IPAddress': '192.168.1.42',
                'LinkLayerAddress': '92-44-95-A2-84-62',
                'InterfaceAlias': 'Ethernet 4',
                'State': 4,
            },
            {
                'IPAddress': '239.255.255.250',
                'LinkLayerAddress': '01-00-5E-7F-FF-FA',
                'InterfaceAlias': 'Ethernet 4',
                'State': 6,
            },
        ]

        async def run_test():
            with patch('backend.services.edge_discovery._run_powershell_json', return_value=raw_neighbors), patch('backend.services.edge_discovery._probe_network_target', return_value=None), patch('backend.services.edge_discovery.platform.system', return_value='Windows'):
                return await scan_network_neighbors()

        devices = asyncio.run(run_test())
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['connection'], 'network')
        self.assertEqual(devices[0]['status'], 'visible')

    def test_build_capabilities_exposes_control_plane_flags(self):
        caps = _build_capabilities({
            'id': 'usb-COM14',
            'family': 'uart-bridge',
            'chip': 'WCH CH340',
            'connection': 'usb',
            'port': 'COM14',
            'status': 'detected',
        })

        self.assertTrue(caps['console'])
        self.assertTrue(caps['chip_detect'])
        self.assertIn('uart', caps['protocols'])
        self.assertIn('serial', caps['transport_modes'])


if __name__ == '__main__':
    unittest.main()
