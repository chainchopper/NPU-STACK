"""Verify dataset loads and inspect structure."""
from datasets import load_dataset

ds = load_dataset("json", data_files="J:/NPU-STACK/datasets/train_multimodal.jsonl", split="train")
print(f"Loaded: {len(ds)} samples OK")

# Check one multimodal entry
mm = ds[250]
print(f"Entry 250 has {len(mm['messages'])} messages")
for m in mm["messages"]:
    c = m["content"]
    if isinstance(c, list):
        types = [p["type"] for p in c]
        print(f"  {m['role']}: list[{types}]")
    else:
        print(f"  {m['role']}: {type(c).__name__} (BAD!)")

# Verify all images exist
from pathlib import Path
for i in range(250, len(ds)):
    for m in ds[i]["messages"]:
        if isinstance(m["content"], list):
            for p in m["content"]:
                if p.get("type") == "image":
                    img = Path(p["image"])
                    assert img.exists(), f"MISSING: {p['image']}"
print("All image paths verified")
