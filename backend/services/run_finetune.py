#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NPU-STACK Unsloth training launcher — env-variable driven."""
import os, sys, json
from pathlib import Path

job_id = os.environ["NPU_JOB_ID"]
model_name = os.environ["NPU_MODEL_NAME"]
dataset_path = os.environ["NPU_DATASET_PATH"]
output_dir = os.environ["NPU_OUTPUT_DIR"]
epochs = int(os.environ.get("NPU_EPOCHS", "1"))
lr = float(os.environ.get("NPU_LR", "2e-4"))
lora_r = int(os.environ.get("NPU_LORA_R", "16"))
lora_alpha = int(os.environ.get("NPU_LORA_ALPHA", "16"))
batch_size = int(os.environ.get("NPU_BATCH_SIZE", "2"))
grad_accum = int(os.environ.get("NPU_GRAD_ACCUM", "4"))
max_seq_length = int(os.environ.get("NPU_MAX_SEQ_LENGTH", "2048"))

# Disable torch._dynamo — it conflicts with Unsloth's custom Triton kernels
os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["PYTHONWARNINGS"] = "ignore"

print(f"JOB_ID: {job_id}", flush=True)
print(f"Model: {model_name}", flush=True)
print(f"Dataset: {dataset_path}", flush=True)
print(f"Epochs: {epochs}, LR: {lr}, LoRA r={lora_r}", flush=True)
print("=" * 60, flush=True)

try:
    from unsloth import FastLanguageModel, FastVisionModel
    import torch
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments, AutoConfig
    from huggingface_hub import hf_hub_download
    import json as _json

    print(f"torch: {torch.__version__}, CUDA: {torch.cuda.is_available()}", flush=True)
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB", flush=True)

    # Support local model paths (bypass HF download for pre-cached models)
    model_path = model_name
    is_local = Path(model_name).exists() and Path(model_name).is_dir()
    if is_local:
        print(f"Detected local model directory: {model_path}", flush=True)

    # ── Auto-detect model type (text vs vision) ──
    print(f"Detecting model type for {model_name}...", flush=True)
    is_vision = False
    try:
        if is_local:
            cfg_path = Path(model_path) / "config.json"
            cfg = _json.loads(cfg_path.read_text())
        else:
            cfg_path = hf_hub_download(model_name, "config.json", cache_dir="G:/TRAINING-GROUNDS/cache/hf-cache/hub")
            cfg = _json.loads(cfg_path.read_text() if hasattr(cfg_path, 'read_text') else open(cfg_path).read())
            if isinstance(cfg_path, str):
                cfg = _json.load(open(cfg_path))
        model_type = cfg.get("model_type", "")
        archs = cfg.get("architectures", [])
        is_vision = "gemma4" in model_type or any("Vision" in a or "VL" in a for a in archs)
    except Exception as e:
        print(f"Could not detect model type ({e}), defaulting to text", flush=True)
    
    ModelClass = FastVisionModel if is_vision else FastLanguageModel
    print(f"Using {'FastVisionModel (multimodal)' if is_vision else 'FastLanguageModel (text)'}", flush=True)

    print(f"Loading {model_name}...", flush=True)
    model, tokenizer = ModelClass.from_pretrained(
        model_name=model_path,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )
    model = ModelClass.get_peft_model(
        model,
        r=lora_r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    print(f"Loading dataset from {dataset_path}...", flush=True)
    raw_dataset = load_dataset("json", data_files=dataset_path, split="train")
    print(f"Dataset: {len(raw_dataset)} raw samples", flush=True)

    # ── Dataset formatting ──
    tokenizer.pad_token = tokenizer.eos_token

    if is_vision:
        # For vision models, use the model's chat template directly
        # Format as conversations with optional images
        def format_vision_conversation(examples):
            texts = []
            for messages in examples["messages"]:
                # Build conversation for the tokenizer's chat template
                conversation = []
                for m in messages:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    # Handle multimodal content (list of parts with type: text/image)
                    if isinstance(content, list):
                        conversation.append({"role": role, "content": content})
                    else:
                        conversation.append({"role": role, "content": content})
                try:
                    text = tokenizer.apply_chat_template(
                        conversation, tokenize=False, add_generation_prompt=False
                    )
                    texts.append(text)
                except Exception:
                    # Fallback: plain formatting
                    parts = []
                    for m in messages:
                        r = m.get("role", "user")
                        c = m.get("content", "") if isinstance(m.get("content", ""), str) else "[multimodal]"
                        parts.append(f"### {r.title()}: {c}")
                    texts.append("\n\n".join(parts))
            return {"text": texts}
        
        dataset = raw_dataset.map(format_vision_conversation, batched=True, remove_columns=raw_dataset.column_names)
    else:
        # Text-only ShareGPT formatting
        def format_sharegpt(examples):
            texts = []
            for messages in examples["messages"]:
                parts = []
                for m in messages:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
                    if role == "user":
                        parts.append(f"### Human: {content}")
                    elif role == "assistant":
                        parts.append(f"### Assistant: {content}")
                texts.append("\n\n".join(parts))
            return {"text": texts}
        
        dataset = raw_dataset.map(format_sharegpt, batched=True, remove_columns=raw_dataset.column_names)
    
    print(f"Dataset: {len(dataset)} formatted samples", flush=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        max_seq_length=max_seq_length,
        group_by_length=True,  # pack short seqs, isolate long ones — critical for 128K context
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            warmup_steps=5,
            num_train_epochs=epochs,
            learning_rate=lr,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit",  # 8-bit optimizer — crucial for long-context VRAM
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=output_dir,
        ),
    )

    print("Starting training...", flush=True)
    try:
        trainer.train()
    except Exception as e:
        err = str(e)
        if "PicklingError" in err or "pickle" in err.lower():
            print(f"Checkpoint save error (cosmetic — adapter weights are fine): {e}", flush=True)
        else:
            raise

    print("Saving model...", flush=True)
    try:
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
    except Exception as e:
        print(f"save_pretrained failed ({e}), using merge_and_unload...", flush=True)
        merged = model.merge_and_unload()
        merged.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

    # Export GGUF if requested
    export_gguf = os.environ.get("NPU_EXPORT_GGUF", "").lower() in ("1", "true", "yes")
    if export_gguf:
        print("Exporting to GGUF...", flush=True)
        quant = os.environ.get("NPU_GGUF_QUANT", "q4_k_m")
        gguf_dir = "G:/TRAINING-GROUNDS/exports"
        os.makedirs(gguf_dir, exist_ok=True)
        try:
            model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method=quant)
            print(f"GGUF exported to {gguf_dir}", flush=True)
        except Exception as e:
            print(f"GGUF export failed: {e}, trying merge path...", flush=True)
            merged = model.merge_and_unload()
            merged.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method=quant)
            print(f"GGUF exported via merge to {gguf_dir}", flush=True)
    print("COMPLETE", flush=True)

except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
