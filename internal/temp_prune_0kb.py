import os
import shutil

TARGET_DIR = r"F:\COMFY-XEASY\ComfyUI\models"
DELETE_DIR = os.path.join(TARGET_DIR, "_TO_DELETE_0KB")
LOG_FILE = os.path.join(TARGET_DIR, "prune_0kb_log.txt")

def find_and_move_0kb_files():
    if not os.path.exists(TARGET_DIR):
        print(f"Directory not found: {TARGET_DIR}")
        return

    os.makedirs(DELETE_DIR, exist_ok=True)
    
    zero_kb_files = []
    
    # Walk through the directory and find 0KB files
    for root, dirs, files in os.walk(TARGET_DIR):
        # Skip the delete directory itself
        if "_TO_DELETE" in root:
            continue
            
        for file in files:
            file_path = os.path.join(root, file)
            try:
                # Check file size
                if os.path.getsize(file_path) == 0:
                    zero_kb_files.append(file_path)
            except OSError as e:
                print(f"Error accessing {file_path}: {e}")
                
    if not zero_kb_files:
        print("No 0KB files found!")
        return

    print(f"Found {len(zero_kb_files)} 0KB files. Moving them to {DELETE_DIR}...")
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"--- 0KB FILE PRUNE LOG ---\n")
        f.write(f"Total 0KB Files Found: {len(zero_kb_files)}\n\n")
        
        for file_path in zero_kb_files:
            rel_path = os.path.relpath(file_path, TARGET_DIR)
            
            # Construct destination path preserving structure if desired, or flat
            # We'll use a flat structure with path components in the filename to avoid collisions
            safe_name = rel_path.replace(os.sep, "___")
            dest_path = os.path.join(DELETE_DIR, safe_name)
            
            try:
                shutil.move(file_path, dest_path)
                log_line = f"MOVED: {rel_path} -> _TO_DELETE_0KB\\{safe_name}\n"
                f.write(log_line)
                print(f"Moved {os.path.basename(file_path)}")
            except Exception as e:
                err_line = f"ERROR moving {rel_path}: {e}\n"
                f.write(err_line)
                print(err_line.strip())

    print(f"\nDone! Moved {len(zero_kb_files)} files to {DELETE_DIR}.")
    print(f"Check {LOG_FILE} for details.")

if __name__ == "__main__":
    find_and_move_0kb_files()
