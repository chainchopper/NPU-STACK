#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NPU-STACK GGUF exporter — base model + LoRA merge + GGUF export."""
import os, sys, glob
from pathlib import Path

ckpt = Path(os.environ.get("NPU_CHECKPOINT_DIR", ""))
quant = os.environ.get("NPU_GGUF_QUANT", "q4_k_m")
out_dir = os.environ.get("NPU_OUTPUT_DIR", ".")
out_name = os.environ.get("NPU_OUTPUT_NAME", "model.gguf")

# Auto-detect base model from checkpoint directory name
ckpt_parent = ckpt.parent.name.lower()
MODEL_MAP = {
    "magneto-tiny": "unsloth/tinyllama-bnb-4bit",
    "magneto-tiny-3e": "unsloth/tinyllama-bnb-4bit",
    "magneto-llama3.2-3b": "unsloth/llama-3.2-3b-bnb-4bit",
}
base_model = "unsloth/llama-3.2-3b-bnb-4bit"
for key, val in MODEL_MAP.items():
    if key in ckpt_parent:
        base_model = val
        break

print(f"Base model: {base_model}", flush=True)
print(f"Checkpoint: {ckpt}", flush=True)
print(f"Quant: {quant}", flush=True)

try:
    from unsloth import FastLanguageModel
    from peft import PeftModel
    import torch

    print(f"Loading base {base_model}...", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model, max_seq_length=2048, dtype=None, load_in_4bit=True,
    )

    print(f"Loading LoRA from {ckpt}...", flush=True)
    model = PeftModel.from_pretrained(model, str(ckpt))
    print("Merging adapter into base...", flush=True)
    model = model.merge_and_unload()

    print(f"Exporting GGUF ({quant})...", flush=True)
    model.save_pretrained_gguf(out_dir, tokenizer, quantization_method=quant)

    gguf_files = glob.glob(os.path.join(out_dir, "*.gguf"))
    if gguf_files:
        target = os.path.join(out_dir, out_name)
        os.rename(gguf_files[0], target)
        size_mb = os.path.getsize(target) / (1024 * 1024)
        print(f"OK: {target} ({size_mb:.1f} MB)", flush=True)
    else:
        print("FAIL: no .gguf produced", flush=True)

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
