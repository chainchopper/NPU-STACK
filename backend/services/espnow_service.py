"""ESP-NOW service — discover, build, and flash ESP-NOW firmware.

ESP-NOW library baked into NPU-STACK at libraries/esp-now-lib/.
Provides firmware discovery, example listing, IDF build commands,
and flash-ready firmware paths for Nirvana's fleet operations.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
ESPNOW_LIB_DIR = REPO_ROOT / "libraries" / "esp-now-lib"
ESPNOW_SRC_DIR = ESPNOW_LIB_DIR / "src"
ESPNOW_EXAMPLES_DIR = ESPNOW_LIB_DIR / "examples"

# ESP-IDF tool paths (defaults, overridable via env)
IDF_PATH = os.getenv("IDF_PATH", "")
IDF_PYTHON = os.getenv("IDF_PYTHON", os.getenv("ESP_IDF_PYTHON", "python"))
ESPPORT = os.getenv("ESPPORT", "")


def espnow_available() -> bool:
    """Check if the ESP-NOW library is baked into the workspace."""
    return ESPNOW_LIB_DIR.exists() and (ESPNOW_LIB_DIR / "CMakeLists.txt").exists()


def list_modules() -> Dict[str, Any]:
    """List all ESP-NOW source modules."""
    if not ESPNOW_SRC_DIR.exists():
        return {"modules": [], "count": 0, "path": str(ESPNOW_SRC_DIR)}

    modules = []
    for d in sorted(ESPNOW_SRC_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            has_include = (d / "include").exists()
            has_src = (d / "src").exists() or any(
                f.suffix in (".c", ".cpp") for f in d.iterdir() if f.is_file()
            )
            modules.append({
                "name": d.name,
                "has_include": has_include,
                "has_source": has_src,
            })

    return {
        "modules": modules,
        "count": len(modules),
        "path": str(ESPNOW_SRC_DIR),
    }


def list_examples() -> Dict[str, Any]:
    """List all ESP-NOW example projects."""
    if not ESPNOW_EXAMPLES_DIR.exists():
        return {"examples": [], "count": 0, "path": str(ESPNOW_EXAMPLES_DIR)}

    examples = []
    for d in sorted(ESPNOW_EXAMPLES_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            cmake = (d / "CMakeLists.txt").exists()
            readme = (d / "README.md").exists()
            sdkconfig = (d / "sdkconfig.defaults").exists()
            examples.append({
                "name": d.name,
                "has_cmake": cmake,
                "has_readme": readme,
                "has_sdkconfig": sdkconfig,
                "path": str(d.relative_to(REPO_ROOT)),
            })

    return {
        "examples": examples,
        "count": len(examples),
        "path": str(ESPNOW_EXAMPLES_DIR),
    }


def get_example_detail(name: str) -> Optional[Dict[str, Any]]:
    """Get details for a specific example, including its README."""
    example_dir = ESPNOW_EXAMPLES_DIR / name
    if not example_dir.exists() or not example_dir.is_dir():
        return None

    readme_path = example_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8", errors="replace") if readme_path.exists() else ""

    source_files = []
    for f in sorted(example_dir.rglob("*")):
        if f.is_file() and f.suffix in (".c", ".cpp", ".h", ".py", ".md"):
            source_files.append(str(f.relative_to(example_dir)))

    return {
        "name": name,
        "path": str(example_dir.relative_to(REPO_ROOT)),
        "readme": readme[:2000],
        "source_files": source_files[:30],
        "file_count": len(source_files),
    }


def idf_available() -> bool:
    """Check if ESP-IDF toolchain is available."""
    if IDF_PATH and Path(IDF_PATH).exists():
        return True
    idf_py = shutil.which("idf.py")
    return idf_py is not None


def build_command(example: str, target: str = "esp32", port: str = "") -> Dict[str, Any]:
    """Return the build command for an ESP-NOW example."""
    example_dir = ESPNOW_EXAMPLES_DIR / example
    if not example_dir.exists():
        return {"error": f"Example not found: {example}", "available": False}

    idf_cmd = "idf.py" if shutil.which("idf.py") else f"{IDF_PATH}/tools/idf.py"

    commands = {
        "set_target": f"{idf_cmd} set-target {target}",
        "build": f"{idf_cmd} build",
        "flash": f"{idf_cmd} -p {port or 'ESPPORT'} flash",
        "monitor": f"{idf_cmd} -p {port or 'ESPPORT'} monitor",
        "full": f"{idf_cmd} set-target {target} && {idf_cmd} build && {idf_cmd} -p {port or 'ESPPORT'} flash",
    }

    return {
        "example": example,
        "target": target,
        "port": port or "auto-detect",
        "directory": str(example_dir),
        "commands": commands,
        "idf_available": idf_available(),
        "idf_path": IDF_PATH or "not set",
    }


def get_firmware_binaries(example: str) -> Dict[str, Any]:
    """Find built firmware binaries for an example."""
    example_dir = ESPNOW_EXAMPLES_DIR / example
    build_dir = example_dir / "build"

    binaries = []
    if build_dir.exists():
        for f in sorted(build_dir.rglob("*.bin")):
            binaries.append({
                "name": f.name,
                "path": str(f.relative_to(REPO_ROOT)),
                "size": f.stat().st_size,
                "offset": _guess_offset(f.name),
            })

    return {
        "example": example,
        "build_dir": str(build_dir.relative_to(REPO_ROOT)) if build_dir.exists() else None,
        "built": len(binaries) > 0,
        "binaries": binaries,
        "count": len(binaries),
    }


def _guess_offset(filename: str) -> str:
    """Guess flash offset from binary filename convention."""
    name = filename.lower()
    if "bootloader" in name:
        return "0x1000"
    if "partition" in name:
        return "0x8000"
    if "ota_data" in name:
        return "0xe000"
    if "app" in name or name.endswith(".bin"):
        return "0x10000"
    return "unknown"
