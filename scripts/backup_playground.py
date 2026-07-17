"""Backup Adafruit Playground CIRCUITPY drive — read-only."""
import os, shutil, time
from pathlib import Path

BACKUP = Path("J:/NPU-STACK/backend/data/firmware_backups/adafruit-playground-" + time.strftime("%Y%m%d-%H%M%S"))
BACKUP.mkdir(parents=True, exist_ok=True)

# Use Windows API to find removable drives instantly (no hang on missing drives)
import ctypes
DRIVE_REMOVABLE = 2
found_removable = []

for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
    drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\")
    if drive_type == DRIVE_REMOVABLE:
        path = f"{letter}:\\"
        boot = Path(path) / "boot_out.txt"
        code = Path(path) / "code.py"
        if boot.exists() or code.exists():
            print(f"CIRCUITPY FOUND at {path}")
            if boot.exists():
                print(boot.read_text(encoding="utf-8", errors="replace").strip())
            for f in sorted(Path(path).iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    dest = BACKUP / f.name
                    shutil.copy2(str(f), str(dest))
                    print(f"  OK {f.name} ({f.stat().st_size} bytes)")
            files = list(BACKUP.iterdir())
            total = sum(f.stat().st_size for f in files)
            print(f"\nBACKUP COMPLETE: {len(files)} files, {total} bytes")
            print(f"Location: {BACKUP}")
            import sys; sys.exit(0)
        else:
            found_removable.append(f"{letter}: (no CIRCUITPY marker)")

if found_removable:
    print(f"Removable drives found but none are CIRCUITPY: {found_removable}")
else:
    print("No removable drives detected. Try double-tap reset again.")
