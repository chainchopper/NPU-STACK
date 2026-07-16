"""Backup Adafruit Playground CIRCUITPY drive — read-only."""
import os, shutil, time
from pathlib import Path

BACKUP = Path("J:/NPU-STACK/backend/data/firmware_backups/adafruit-playground-" + time.strftime("%Y%m%d-%H%M%S"))
BACKUP.mkdir(parents=True, exist_ok=True)

# Only check known removable drives on this system (D, E, F)
for letter in ["D", "E", "F", "G"]:
    path = f"{letter}:\\"
    # Skip if drive doesn't exist
    if not os.path.exists(path):
        continue
    boot = Path(path) / "boot_out.txt"
    code = Path(path) / "code.py"
    if boot.exists() or code.exists():
        print(f"CIRCUITPY FOUND at {path}")
        if boot.exists():
            print(boot.read_text(encoding="utf-8", errors="replace").strip())
        for f in Path(path).iterdir():
            if f.is_file() and not f.name.startswith("."):
                dest = BACKUP / f.name
                shutil.copy2(str(f), str(dest))
                print(f"  OK {f.name} ({f.stat().st_size} bytes)")
        # Count
        files = list(BACKUP.iterdir())
        total = sum(f.stat().st_size for f in files)
        print(f"\nBACKUP COMPLETE: {len(files)} files, {total} bytes")
        print(f"Location: {BACKUP}")
        import sys; sys.exit(0)

print("CIRCUITPY not found on D:, E:, F:, or G:")
print("The Playground may need to be double-tapped again, or check Windows Explorer for the drive letter.")
