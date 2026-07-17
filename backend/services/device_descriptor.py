"""NPU-STACK Device Descriptor Branding — USB descriptor customization for enterprise fleet.

Allows fleet deployers to set custom USB vendor/product strings, serial numbers,
and device identifiers during the flash process. Configured via .env or settings UI.

Baked into the flash pipeline — every NPU agent gets branded descriptors on first flash.
"""
from __future__ import annotations

import json, os, struct, sys, time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / ".env"


# ── Default NPU-STACK Branding ────────────────────────────────────────────

DEFAULT_BRAND = {
    "vendor": "Fanalogy",
    "vendor_short": "NPU-STACK",
    "device_prefix": "Nirvana",
    "fleet_prefix": "npu-fleet",
    "usb_vid": 0x303A,   # Use target chip VID (Espressif/Rockchip/etc)
    "usb_pid": 0x8001,   # NPU-STACK custom PID
    "manufacturer": "Fanalogy — NPU-STACK Fleet",
    "product_template": "Nirvana Fleet {chip} — {device_id}",
    "serial_template": "NPU-{device_id}-{short_hash}",
    "mqtt_discovery_topic": "npu-fleet/discovery",
    "zeroconf_service": "_npu-fleet._tcp.local.",
}


# ── Load from .env ─────────────────────────────────────────────────────────

def load_brand_config() -> Dict[str, Any]:
    """Load branding from .env file, falling back to defaults."""
    brand = dict(DEFAULT_BRAND)

    if not ENV_FILE.exists():
        return brand

    try:
        env_vars = {}
        for line in ENV_FILE.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env_vars[key.strip()] = val.strip().strip('"').strip("'")

        # Map .env vars to brand dict
        env_map = {
            "NPU_FLEET_VENDOR": "vendor",
            "NPU_FLEET_PREFIX": "device_prefix",
            "NPU_FLEET_MANUFACTURER": "manufacturer",
            "NPU_FLEET_PRODUCT_TEMPLATE": "product_template",
            "NPU_FLEET_SERIAL_TEMPLATE": "serial_template",
            "NPU_FLEET_MQTT_PREFIX": "fleet_prefix",
        }

        for env_key, brand_key in env_map.items():
            if env_key in env_vars:
                brand[brand_key] = env_vars[env_key]

    except Exception:
        pass

    return brand


# ── Descriptor Generator ───────────────────────────────────────────────────

def generate_device_descriptor(
    device_id: str,
    chip: str,
    platform: str,
    brand: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate branded USB/network descriptors for a fleet device.

    Returns a dict that gets injected into the device config (npu_config.json)
    during the flash pipeline.
    """
    if brand is None:
        brand = load_brand_config()

    short_hash = _short_hash(device_id + chip + str(time.time()))

    descriptor = {
        # USB descriptors (used by boards that support dynamic USB strings)
        "usb": {
            "manufacturer": brand["manufacturer"],
            "product": brand["product_template"].format(chip=chip, device_id=device_id),
            "serial": brand["serial_template"].format(device_id=device_id, short_hash=short_hash),
        },
        # Network discovery descriptors
        "discovery": {
            "mqtt_topic": f"{brand['fleet_prefix']}/status/{device_id}",
            "mdns_name": f"{device_id}.{brand['zeroconf_service']}",
            "ble_name": f"{brand['device_prefix']} {device_id[:8]}",
            "wifi_hostname": f"{brand['device_prefix'].lower()}-{short_hash}",
        },
        # Metadata
        "meta": {
            "fleet_version": "1.0.0",
            "brand": brand["vendor"],
            "brand_short": brand["vendor_short"],
            "platform": platform,
            "chip": chip,
            "flashed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }

    return descriptor


def generate_npu_config(
    device_id: str,
    chip: str,
    platform: str,
    mqtt_broker: str = "127.0.0.1",
    mqtt_port: int = 1883,
    wifi_ssid: str = "",
    wifi_pass: str = "",
    brand: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate the full npu_config.json that gets baked into firmware bundles."""
    if brand is None:
        brand = load_brand_config()

    descriptor = generate_device_descriptor(device_id, chip, platform, brand)

    return {
        "device_id": device_id,
        "mqtt_broker": mqtt_broker,
        "mqtt_port": mqtt_port,
        "wifi_ssid": wifi_ssid,
        "wifi_password": wifi_pass,
        "telemetry_interval": 5,
        "brand": descriptor,
    }


# ── Brand Summary Endpoint ─────────────────────────────────────────────────

def get_brand_summary() -> Dict[str, Any]:
    """Return current branding configuration for the UI settings panel."""
    brand = load_brand_config()
    return {
        "brand": brand,
        "env_file": str(ENV_FILE),
        "env_exists": ENV_FILE.exists(),
        "customizable_fields": [
            "NPU_FLEET_VENDOR", "NPU_FLEET_PREFIX", "NPU_FLEET_MANUFACTURER",
            "NPU_FLEET_PRODUCT_TEMPLATE", "NPU_FLEET_SERIAL_TEMPLATE",
            "NPU_FLEET_MQTT_PREFIX",
        ],
    }


def update_brand_config(updates: Dict[str, str]) -> Dict[str, Any]:
    """Update branding configuration in .env file (creates if not exists)."""
    env_map = {
        "vendor": "NPU_FLEET_VENDOR",
        "device_prefix": "NPU_FLEET_PREFIX",
        "manufacturer": "NPU_FLEET_MANUFACTURER",
        "product_template": "NPU_FLEET_PRODUCT_TEMPLATE",
        "serial_template": "NPU_FLEET_SERIAL_TEMPLATE",
        "fleet_prefix": "NPU_FLEET_MQTT_PREFIX",
    }

    # Read existing .env (preserve non-brand vars)
    existing = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    # Apply updates
    for key, env_key in env_map.items():
        if key in updates:
            existing[env_key] = updates[key]

    # Write back
    lines = [
        "# NPU-STACK Fleet Branding Configuration",
        "# Generated by NPU-STACK Device Descriptor Service",
        f"# {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    # Add fleet branding section
    lines.append("# ── Fleet Branding ──")
    for env_key in env_map.values():
        if env_key in existing:
            lines.append(f'{env_key}="{existing[env_key]}"')

    # Re-add any non-brand lines from original
    for k, v in existing.items():
        if k not in env_map.values():
            lines.append(f'{k}="{v}"')

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"success": True, "brand": load_brand_config()}


def _short_hash(s: str, length: int = 8) -> str:
    """Short hex hash for device identifiers."""
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()[:length]
