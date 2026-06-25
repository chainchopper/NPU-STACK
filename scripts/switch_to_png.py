#!/usr/bin/env python3
"""Switch image paths from .svg to .png in the dataset."""
import json
from pathlib import Path

src = Path(r"J:\NPU-STACK\datasets\train_multimodal.jsonl")
entries = [json.loads(line) for line in src.read_text(encoding="utf-8").strip().split("\n")]

for entry in entries:
    for msg in entry["messages"]:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image":
                    part["image"] = part["image"].replace(".svg", ".png")

src.write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
    encoding="utf-8",
)

# Verify
for entry in entries[-1:]:
    for msg in entry["messages"]:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image":
                    exists = Path(part["image"]).exists()
                    print(f"{part['image']}  exists={exists}")

print("Done")
