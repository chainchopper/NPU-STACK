import os
import shutil
from collections import defaultdict

def main():
    models_dir = r"F:\COMFY-XEASY\ComfyUI\models"
    delete_dir = os.path.join(models_dir, "_TO_DELETE")

    if not os.path.exists(delete_dir):
        os.makedirs(delete_dir)

    # Group by lowercase filename
    file_groups = defaultdict(list)

    print("Scanning models directory...")
    for root, dirs, files in os.walk(models_dir):
        if "_TO_DELETE" in root:
            continue
        for file in files:
            if file.endswith(('.safetensors', '.ckpt', '.pt', '.bin', '.pth', '.onnx', '.gguf', '.sft')):
                filepath = os.path.join(root, file)
                size = os.path.getsize(filepath)
                
                # Use lowercase for grouping to avoid case sensitivity issues
                name_key = file.lower()
                file_groups[name_key].append({'path': filepath, 'size': size, 'original_name': file})

    total_moved = 0
    total_space_freed = 0
    moved_log = []

    print(f"Found {len(file_groups)} unique model names.")
    print("Evaluating duplicates and moving to _TO_DELETE...")

    for name_key, files in file_groups.items():
        if len(files) > 1:
            # Sort files by size (descending), then by path depth (ascending), then by path length (ascending)
            files.sort(key=lambda x: (-x['size'], x['path'].count(os.sep), len(x['path'])))
            
            winner = files[0]
            losers = files[1:]
            
            for loser in losers:
                loser_path = loser['path']
                rel_path = os.path.relpath(loser_path, models_dir)
                target_path = os.path.join(delete_dir, rel_path)
                
                target_dir = os.path.dirname(target_path)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                    
                try:
                    shutil.move(loser_path, target_path)
                    total_moved += 1
                    total_space_freed += loser['size']
                    
                    moved_log.append(f"MOVED: {loser_path} (Size: {loser['size'] / (1024**3):.2f} GB)\n  KEPT: {winner['path']} (Size: {winner['size'] / (1024**3):.2f} GB)\n")
                except Exception as e:
                    print(f"Error moving {loser_path}: {e}")

    log_path = os.path.join(models_dir, "prune_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Total files moved: {total_moved}\n")
        f.write(f"Total space to be freed: {total_space_freed / (1024**3):.2f} GB\n\n")
        f.write("\n".join(moved_log))

    print(f"Done. Moved {total_moved} files.")
    print(f"Reclaimable space: {total_space_freed / (1024**3):.2f} GB")
    print(f"Please check the _TO_DELETE folder and {log_path} for details.")

if __name__ == '__main__':
    main()
