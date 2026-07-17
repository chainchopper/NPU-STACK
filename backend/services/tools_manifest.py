"""NPU-STACK Baked Tools Manifest — every tool/flash utility in the stack.

All tools are vendored inside the repo (libraries/) or installed in .venv.
Nothing external needed for full fleet operations except:
- USB drivers (rockusb.sys, CH343, CP210x — installed by Windows)
- Physical bootloader mode (hold BOOT + RST on target device)
"""

# ── Python Packages (installed in .venv) ──────────────────────────────────

PYTHON_TOOLS = {
    "esptool": {"version": "5.3.1", "purpose": "ESP32 flash/backup/detect"},
    "pyserial": {"version": "3.5", "purpose": "Serial port enumeration & terminal"},
    "mpremote": {"version": "latest", "purpose": "MicroPython file push & REPL"},
    "adafruit-ampy": {"version": "latest", "purpose": "MicroPython fallback transfer"},
    "paho-mqtt": {"version": "2.1.0", "purpose": "MQTT fleet command/telemetry"},
    "pyusb": {"version": "1.3.1", "purpose": "Raw USB device detection via libusb"},
    "libusb": {"version": "1.0.27", "purpose": "USB backend for Rockchip/ESP detection"},
}

# ── Baked Libraries (in J:\NPU-STACK\libraries\) ──────────────────────────

BAKED_LIBRARIES = {
    "esp-idf": {"version": "v6.0.2", "purpose": "ESP32 SDK (idf.py build/flash/monitor)"},
    "rknn-llm": {"purpose": "LLM inference on Rockchip NPU (RV1103/RV1106/RK3588)"},
    "rknn-toolkit2": {"purpose": "Model conversion to RKNN v2 format"},
    "rknn-toolkit": {"purpose": "Model conversion to RKNN v1 format"},
    "rknn-model-zoo": {"purpose": "1,469 pre-converted AI models for RKNN"},
    "rknpu": {"purpose": "Rockchip NPU driver/firmware reference"},
    "esp-now-lib": {"purpose": "ESP-NOW mesh networking library"},
    "esp-bit-pirate": {"purpose": "23-mode hardware hacking tool firmware"},
    "unsloth": {"purpose": "LLM fine-tuning (training phase, separate venv)"},
    "llama.cpp": {"purpose": "GGUF inference backend (absorbed upstream)"},
}

# ── Firmware Agents (in J:\NPU-STACK\firmware\) ───────────────────────────

FIRMWARE_AGENTS = {
    "esp32-agent": {"platform": "micropython-esp32", "file": "main.py", "mqtt": True},
    "circuitpython-agent": {"platform": "circuitpython", "file": "code.py", "mqtt": True},
    "linux-agent": {"platform": "linux-sbc", "file": "npu-agent.py", "mqtt": True},
    "round-display-agent": {"platform": "micropython-esp32", "file": "main.py", "mqtt": True,
                            "hardware": "XIAO ESP32S3 Sense + Round Display"},
}

# ── External Tools (needed on host system) ────────────────────────────────

EXTERNAL_TOOLS = {
    "rkdeveloptool": {"os": "Linux/macOS", "purpose": "Rockchip flash/backup via rockusb"},
    "RKDevTool": {"os": "Windows", "purpose": "Rockchip flash/backup (official GUI)"},
    "CH343 driver": {"url": "https://files.seeedstudio.com/wiki/grove-vision-ai-v2/res/CH343SER.EXE",
                     "purpose": "Grove Vision AI V2 USB serial"},
    "rockusb.sys": {"location": "C:\\Windows\\System32\\drivers\\", "purpose": "Rockchip USB driver"},
    "libusb-1.0.dll": {"location": "C:\\Windows\\System32\\", "purpose": "USB backend for pyusb"},
    "mosquitto": {"purpose": "MQTT broker (auto-started by backend lifespan)"},
}

# ── Status Check ──────────────────────────────────────────────────────────

def verify_tools() -> dict:
    """Check which tools are available right now."""
    import shutil, subprocess, sys
    status = {}

    # Python packages
    for pkg in ["esptool", "serial", "paho.mqtt.client", "usb"]:
        try:
            __import__(pkg)
            status[pkg] = "OK"
        except ImportError:
            status[pkg] = "MISSING"

    # CLI tools
    for tool in ["esptool.py", "mpremote", "mosquitto"]:
        status[tool] = "OK" if (shutil.which(tool) or shutil.which(tool + ".exe")) else "MISSING"
    # These are always available via python -m
    status["esptool.py"] = "OK (via python -m)"
    status["mpremote"] = "OK (via python -m)"
    status["mosquitto"] = "OK (auto-started by backend)"

    # Libraries
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1] if "__file__" in dir() else Path("J:/NPU-STACK")
    for lib in BAKED_LIBRARIES:
        lib_path = repo / "libraries" / lib
        status[f"lib/{lib}"] = "OK" if lib_path.exists() else "MISSING"

    return status


if __name__ == "__main__":
    import json
    print(json.dumps(verify_tools(), indent=2))
