#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NPU-STACK GGUF exporter — env-variable driven. Runs in .venv-train subprocess."""
import os, sys

ckpt = os.environ.get("NPU_CHECKPOINT_DIR", "")
quant = os.environ.get("NPU_GGUF_QUANT", "q4_k_m")
out_dir = os.environ.get("NPU_OUTPUT_DIR", ".")
out_name = os.environ.get("NPU_OUTPUT_NAME", "model.gguf")

print(f"Loading checkpoint from {ckpt}", flush=True)
print(f"Quantization: {quant}", flush=True)

try:
    from unsloth import FastLanguageModel
    import torch

    # Load base + adapter from checkpoint
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ckpt,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    print("Exporting to GGUF...", flush=True)
    model.save_pretrained_gguf(out_dir, tokenizer, quantization_method=quant)
    print(f"GGUF saved to {out_dir}/{out_name}", flush=True)

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERROR: {e}", flush=True)
    sys.exit(1)
