#!/usr/bin/env python3
"""Fix image paths in multimodal dataset."""
import json
from pathlib import Path

src = Path(r"J:\NPU-STACK\datasets\train_multimodal.jsonl")
img_dir = Path(r"J:\NPU-STACK\datasets\images")

entries = [json.loads(line) for line in src.read_text(encoding="utf-8").strip().split("\n")]

fixed = 0
for entry in entries:
    for msg in entry["messages"]:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image":
                    old_path = Path(part["image"])
                    actual = img_dir / (old_path.stem + ".svg")
                    if actual.exists():
                        part["image"] = str(actual).replace("\\", "/")
                        fixed += 1

src.write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
    encoding="utf-8",
)

print(f"Fixed {fixed} image paths")

# Verify
for entry in entries[-3:]:
    for msg in entry["messages"]:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image":
                    exists = Path(part["image"]).exists()
                    print(f"  {part['image']} -> exists={exists}")
