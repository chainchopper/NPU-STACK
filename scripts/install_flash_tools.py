"""Install flash tools for NPU-STACK — downloads/extracts rkdeveloptool and other USB flashing utilities.

Run: python scripts/install_flash_tools.py
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "backend" / "data" / "flash_tools"

# ── Rockchip rkdeveloptool ──

RKDEVELOPTOOL_VERSION = "1.32"
RKDEVELOPTOOL_URLS = {
    "Windows": None,  # No official prebuilt — compile from source or use alternative
    "Linux": f"https://github.com/rockchip-linux/rkdeveloptool/archive/refs/tags/v{RKDEVELOPTOOL_VERSION}.tar.gz",
    "Darwin": f"https://github.com/rockchip-linux/rkdeveloptool/archive/refs/tags/v{RKDEVELOPTOOL_VERSION}.tar.gz",
}

# For Windows, use the Rockchip Driver Assistant + RKDevTool alternative
RKDEVTOOL_WIN_URL = "https://dl.radxa.com/tools/windows/RKDevTool_Release_v3.28.zip"


def _system() -> str:
    system = platform.system()
    if system == "Windows":
        return "Windows"
    elif system == "Darwin":
        return "Darwin"
    return "Linux"


def install_rkdeveloptool():
    """Install rkdeveloptool for current platform."""
    system = _system()
    tools_dir = TOOLS_DIR / "rkdeveloptool"
    tools_dir.mkdir(parents=True, exist_ok=True)

    if system == "Windows":
        print("[NPU-STACK] rkdeveloptool not available as standalone Windows binary.")
        print("[NPU-STACK] Downloading RKDevTool (includes Rockchip USB driver + flash tool)...")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "RKDevTool.zip"
            subprocess.run(["curl", "-L", "-o", str(zip_path), RKDEVTOOL_WIN_URL], check=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tools_dir)
        print(f"[NPU-STACK] RKDevTool extracted to {tools_dir}")
        return True

    # Linux/macOS: compile from source
    print(f"[NPU-STACK] Building rkdeveloptool v{RKDEVELOPTOOL_VERSION} from source...")
    url = RKDEVELOPTOOL_URLS.get(system)
    if not url:
        print(f"[NPU-STACK] No binary for {system}")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "rkdeveloptool.tar.gz"
        subprocess.run(["curl", "-L", "-o", str(archive), url], check=True)
        subprocess.run(["tar", "xzf", str(archive), "-C", tmp], check=True)
        src_dir = next(Path(tmp).glob("rkdeveloptool-*"))
        # Build
        subprocess.run(["autoreconf", "-i"], cwd=src_dir, check=False)
        subprocess.run(["./configure"], cwd=src_dir, check=False)
        subprocess.run(["make", "-j$(nproc)"], cwd=src_dir, check=False)
        shutil.copy(src_dir / "rkdeveloptool", tools_dir / "rkdeveloptool")
        print(f"[NPU-STACK] rkdeveloptool installed at {tools_dir / 'rkdeveloptool'}")
    return True


if __name__ == "__main__":
    print("[NPU-STACK] Installing flash tools...")
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    if install_rkdeveloptool():
        print("[NPU-STACK] rkdeveloptool ready")
    else:
        print("[NPU-STACK] rkdeveloptool SKIPPED (not available for this platform)")

    print("[NPU-STACK] Flash tools installation complete.")
