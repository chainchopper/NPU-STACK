import os
import sys
from collections import defaultdict

directory = r"F:\COMFY-XEASY\ComfyUI\models"
artifact_path = r"C:\Users\iAMBLACK\.gemini\antigravity\brain\aa16632d-b96f-4f68-9c67-ef1ffa4ac827\model_pruning_analysis.md"

print(f"Scanning {directory}...")

by_name = defaultdict(list)

for root, dirs, files in os.walk(directory):
    for f in files:
        if f.startswith('.'):
            continue
        path = os.path.join(root, f)
        try:
            size = os.path.getsize(path)
            by_name[f].append({"path": path, "size": size, "folder": root})
        except OSError:
            pass

# Filter: Same name, multiple files, different sizes
candidates = {}
for name, files in by_name.items():
    if len(files) > 1:
        sizes = {f["size"] for f in files}
        if len(sizes) > 1: # They have different sizes
            folders = {f["folder"] for f in files}
            if len(folders) > 1: # They are in multiple folders
                candidates[name] = files

with open(artifact_path, "w", encoding="utf-8") as f:
    f.write("# Model Pruning Analysis (Same Name, Different Sizes, Multiple Folders)\n\n")
    f.write(f"Found {len(candidates)} filenames that match your criteria.\n\n")
    
    # Sort by total space wasted (rough estimate: size of largest minus size of smallest, or just show them)
    for name in sorted(candidates.keys()):
        files = candidates[name]
        files.sort(key=lambda x: x["size"], reverse=True) # Largest first
        
        f.write(f"### `{name}`\n")
        for idx, file_info in enumerate(files):
            size_mb = file_info["size"] / (1024 * 1024)
            size_gb = file_info["size"] / (1024 * 1024 * 1024)
            size_str = f"{size_gb:.2f} GB" if size_gb > 1 else f"{size_mb:.2f} MB"
            
            note = "  **(Largest - potentially unpruned/FP32)**" if idx == 0 else "  **(Smaller - potentially pruned/FP16/safetensors)**"
            
            f.write(f"- Size: **{size_str}** | Folder: `{file_info['folder']}` {note}\n")
            f.write(f"  - Full Path: `{file_info['path']}`\n")
        f.write("\n")

print(f"Found {len(candidates)} candidates. saved to {artifact_path}")
