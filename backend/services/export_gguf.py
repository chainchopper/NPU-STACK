#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NPU-STACK GGUF exporter — base model + LoRA merge + GGUF export."""
import os, sys, glob
from pathlib import Path

ckpt = Path(os.environ.get("NPU_CHECKPOINT_DIR", ""))
quant = os.environ.get("NPU_GGUF_QUANT", "q4_k_m")
out_dir = os.environ.get("NPU_OUTPUT_DIR", ".")
out_name = os.environ.get("NPU_OUTPUT_NAME", "model.gguf")

# Route GGUF exports to G:\TRAINING-GROUNDS\exports\ by default
if out_dir == "." or "G:" not in out_dir:
    out_dir = "G:/TRAINING-GROUNDS/exports"

# Auto-detect base model from checkpoint directory name
ckpt_parent = ckpt.parent.name.lower()
MODEL_MAP = {
    "magneto-tiny": "unsloth/tinyllama-bnb-4bit",
    "magneto-tiny-3e": "unsloth/tinyllama-bnb-4bit",
    "magneto-llama3.2-3b": "unsloth/llama-3.2-3b-bnb-4bit",
    "magneto-gemma4-e4b": "unsloth/gemma-4-E4B-it-unsloth-bnb-4bit",
    "magneto-qwen3.6-27b": "unsloth/Qwen3.6-27B",
    "magneto-qwen3.5-9b": "unsloth/Qwen3.5-9B-Base",
    "magneto-qwen2.5-7b": "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
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
    from unsloth import FastLanguageModel, FastVisionModel
    from peft import PeftModel
    import torch

    # Detect if model is vision from checkpoint name
    ckpt_lower = ckpt_parent.lower()
    VISION_MODELS = ["gemma", "qwen3.6", "qwen3.5", "qwen3-", "vision"]
    is_vision = any(k in ckpt_lower for k in VISION_MODELS)
    ModelClass = FastVisionModel if is_vision else FastLanguageModel
    print(f"Using {'FastVisionModel' if is_vision else 'FastLanguageModel'}", flush=True)

    print(f"Loading base {base_model}...", flush=True)
    model, tokenizer = ModelClass.from_pretrained(
        model_name=base_model, max_seq_length=2048, dtype=None, load_in_4bit=True,
    )

    print(f"Loading LoRA from {ckpt}...", flush=True)
    model = PeftModel.from_pretrained(model, str(ckpt))
    print("Merging adapter into base...", flush=True)
    model = model.merge_and_unload()

    # ── Save merged model as 16-bit safetensors, then convert via llama.cpp ──
    merge_dir = os.path.join(str(ckpt.parent), "merged")
    os.makedirs(merge_dir, exist_ok=True)
    print(f"Exporting GGUF ({quant}) via llama.cpp convert...", flush=True)

    # Step 1: Save merged model to disk (16-bit safetensors)
    model.save_pretrained(merge_dir, safe_serialization=True)
    tokenizer.save_pretrained(merge_dir)
    print(f"Merged model saved to {merge_dir}", flush=True)

    # Step 2: Convert to GGUF using llama.cpp
    llama_cpp_dir = os.environ.get("LLAMA_CPP_DIR", "J:/NPU-STACK/llama.cpp")
    convert_script = os.path.join(llama_cpp_dir, "convert_hf_to_gguf.py")
    gguf_path = os.path.join(out_dir, out_name.replace(".gguf", f"-{quant}.gguf"))

    import subprocess
    result = subprocess.run(
        [sys.executable, convert_script, merge_dir, "--outfile", gguf_path, "--outtype", "q8_0"],
        capture_output=True, text=True, cwd=llama_cpp_dir, timeout=3600
    )
    if result.returncode != 0:
        print(f"llama.cpp convert failed: {result.stderr[-500:]}", flush=True)
        # Fallback: try Unsloth native save_pretrained_gguf
        print("Falling back to Unsloth save_pretrained_gguf...", flush=True)
        model.save_pretrained_gguf(out_dir, tokenizer, quantization_method=quant)
    else:
        print(result.stdout[-500:], flush=True)

    # Check result
    gguf_files = glob.glob(os.path.join(out_dir, "*.gguf"))
    if gguf_files:
        size_mb = os.path.getsize(gguf_files[0]) / (1024 * 1024)
        print(f"OK: {gguf_files[0]} ({size_mb:.1f} MB)", flush=True)
    else:
        # Check merge_dir too
        gguf_files2 = glob.glob(os.path.join(merge_dir, "*.gguf"))
        if gguf_files2:
            import shutil
            out_path = os.path.join(out_dir, out_name)
            shutil.move(gguf_files2[0], out_path)
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"OK: {out_path} ({size_mb:.1f} MB)", flush=True)
        else:
            print("FAIL: no .gguf produced at all", flush=True)

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
