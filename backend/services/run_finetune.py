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

os.environ["PYTHONWARNINGS"] = "ignore"

print(f"JOB_ID: {job_id}", flush=True)
print(f"Model: {model_name}", flush=True)
print(f"Dataset: {dataset_path}", flush=True)
print(f"Epochs: {epochs}, LR: {lr}, LoRA r={lora_r}", flush=True)
print("=" * 60, flush=True)

try:
    from unsloth import FastLanguageModel
    import torch
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments

    print(f"torch: {torch.__version__}, CUDA: {torch.cuda.is_available()}", flush=True)
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB", flush=True)

    print(f"Loading {model_name}...", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
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
    dataset = load_dataset("json", data_files=dataset_path, split="train")
    print(f"Dataset: {len(dataset)} samples", flush=True)

    tokenizer.pad_token = tokenizer.eos_token

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            warmup_steps=5,
            num_train_epochs=epochs,
            learning_rate=lr,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=output_dir,
        ),
    )

    print("Starting training...", flush=True)
    trainer.train()

    print("Saving model...", flush=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("COMPLETE", flush=True)

except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
