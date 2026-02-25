"""
Fine-Tuning Router — LoRA/QLoRA parameter-efficient fine-tuning.

Endpoints:
  POST /api/finetune/start        — Start a fine-tuning job
  GET  /api/finetune/jobs          — List all fine-tuning jobs
  GET  /api/finetune/status/{id}   — Get job status and metrics
  POST /api/finetune/stop/{id}     — Stop a running job
"""

import os
import time
import uuid
import json
import threading
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Form, Depends
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(prefix="/api/finetune", tags=["fine-tuning"])

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets")
MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(DATASET_DIR, exist_ok=True)

# In-memory job tracking
_jobs: Dict[str, dict] = {}
_job_threads: Dict[str, threading.Thread] = {}


def _run_finetune_job(job_id: str, config: dict):
    """Background fine-tuning worker using PEFT/LoRA."""
    job = _jobs[job_id]
    job["status"] = "running"
    job["started_at"] = time.time()

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
            DataCollatorForLanguageModeling,
        )

        job["log"].append("Loading base model...")
        model_path = config["model_path"]
        model_dir = os.path.dirname(model_path)

        tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            model_dir,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )

        # Apply LoRA if peft is available
        use_lora = config.get("use_lora", True)
        if use_lora:
            try:
                from peft import LoraConfig, get_peft_model, TaskType
                lora_config = LoraConfig(
                    r=config.get("lora_r", 16),
                    lora_alpha=config.get("lora_alpha", 32),
                    target_modules=config.get("target_modules", ["q_proj", "v_proj"]),
                    lora_dropout=config.get("lora_dropout", 0.05),
                    bias="none",
                    task_type=TaskType.CAUSAL_LM,
                )
                model = get_peft_model(model, lora_config)
                job["log"].append(f"LoRA applied: r={lora_config.r}, alpha={lora_config.lora_alpha}")
                trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
                total = sum(p.numel() for p in model.parameters())
                job["log"].append(f"Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.1f}%)")
            except ImportError:
                job["log"].append("peft not installed — training full model (pip install peft for LoRA)")
                use_lora = False

        # Load dataset
        job["log"].append(f"Loading dataset: {config['dataset_path']}")
        dataset_path = config["dataset_path"]

        from datasets import load_dataset
        if dataset_path.endswith(".json") or dataset_path.endswith(".jsonl"):
            dataset = load_dataset("json", data_files=dataset_path, split="train")
        elif dataset_path.endswith(".csv"):
            dataset = load_dataset("csv", data_files=dataset_path, split="train")
        elif dataset_path.endswith(".txt"):
            dataset = load_dataset("text", data_files=dataset_path, split="train")
        else:
            dataset = load_dataset(dataset_path, split="train")

        # Tokenize
        text_column = config.get("text_column", "text")
        def tokenize_fn(examples):
            texts = examples.get(text_column, examples.get("content", examples.get("input", [])))
            if isinstance(texts, str):
                texts = [texts]
            return tokenizer(texts, truncation=True, max_length=config.get("max_length", 512), padding="max_length")

        tokenized_dataset = dataset.map(tokenize_fn, batched=True, remove_columns=dataset.column_names)
        job["log"].append(f"Dataset tokenized: {len(tokenized_dataset)} examples")

        # Training args
        output_dir = os.path.join(MODEL_STORE, f"finetune-{job_id}")
        os.makedirs(output_dir, exist_ok=True)

        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=config.get("epochs", 3),
            per_device_train_batch_size=config.get("batch_size", 4),
            learning_rate=config.get("learning_rate", 2e-4),
            warmup_steps=config.get("warmup_steps", 100),
            logging_steps=10,
            save_steps=500,
            save_total_limit=2,
            fp16=torch.cuda.is_available(),
            report_to="none",
            remove_unused_columns=False,
        )

        data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

        # Custom callback to track metrics
        class MetricsCallback:
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs:
                    job["metrics"].append({
                        "step": state.global_step,
                        "epoch": round(state.epoch, 2) if state.epoch else 0,
                        "loss": logs.get("loss"),
                        "learning_rate": logs.get("learning_rate"),
                    })
                    job["current_step"] = state.global_step
                    job["current_epoch"] = round(state.epoch, 2) if state.epoch else 0

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset,
            data_collator=data_collator,
        )

        job["log"].append("Training started...")
        trainer.train()

        # Save the model
        job["log"].append("Saving fine-tuned model...")
        if use_lora:
            model.save_pretrained(output_dir)
        else:
            model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

        job["status"] = "completed"
        job["completed_at"] = time.time()
        job["output_dir"] = output_dir
        job["log"].append(f"Fine-tuning complete! Model saved to {output_dir}")

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["completed_at"] = time.time()
        job["log"].append(f"Error: {str(e)}")


@router.post("/start")
async def start_finetuning(
    model_id: int = Form(...),
    dataset: str = Form(..., description="Dataset name or path"),
    epochs: int = Form(3),
    batch_size: int = Form(4),
    learning_rate: float = Form(2e-4),
    use_lora: bool = Form(True),
    lora_r: int = Form(16),
    lora_alpha: int = Form(32),
    text_column: str = Form("text"),
    max_length: int = Form(512),
    db: Session = Depends(get_db),
):
    """Start a fine-tuning job with LoRA/QLoRA.
    
    Requires: pip install peft datasets transformers torch
    """
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, f"Model #{model_id} not found")

    # Resolve dataset path
    dataset_path = dataset
    if not os.path.isabs(dataset_path):
        # Check in datasets directory
        for candidate in [
            os.path.join(DATASET_DIR, dataset),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "datasets", dataset),
        ]:
            if os.path.exists(candidate):
                dataset_path = candidate
                break

    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "model_id": model_id,
        "model_name": record.name,
        "dataset": dataset,
        "status": "initializing",
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "output_dir": None,
        "current_step": 0,
        "current_epoch": 0,
        "metrics": [],
        "log": [],
        "config": {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "use_lora": use_lora,
            "lora_r": lora_r,
            "lora_alpha": lora_alpha,
            "text_column": text_column,
            "max_length": max_length,
        },
    }
    _jobs[job_id] = job

    config = {
        "model_path": record.file_path,
        "dataset_path": dataset_path,
        **job["config"],
    }

    thread = threading.Thread(target=_run_finetune_job, args=(job_id, config), daemon=True)
    _job_threads[job_id] = thread
    thread.start()

    return {
        "job_id": job_id,
        "status": "initializing",
        "model": record.name,
        "dataset": dataset,
        "config": job["config"],
    }


@router.get("/jobs")
async def list_jobs():
    """List all fine-tuning jobs."""
    jobs = []
    for job in _jobs.values():
        jobs.append({
            "id": job["id"],
            "model_name": job["model_name"],
            "dataset": job["dataset"],
            "status": job["status"],
            "created_at": job["created_at"],
            "current_step": job["current_step"],
            "current_epoch": job["current_epoch"],
            "error": job["error"],
        })
    return {"jobs": jobs}


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get detailed status and metrics for a fine-tuning job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")

    return {
        "id": job["id"],
        "model_name": job["model_name"],
        "dataset": job["dataset"],
        "status": job["status"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "current_step": job["current_step"],
        "current_epoch": job["current_epoch"],
        "config": job["config"],
        "metrics": job["metrics"][-50:],  # Last 50 entries
        "log": job["log"][-20:],
        "output_dir": job["output_dir"],
        "error": job["error"],
    }


@router.post("/stop/{job_id}")
async def stop_job(job_id: str):
    """Stop a running fine-tuning job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job["status"] != "running":
        return {"status": job["status"], "message": "Job is not running"}

    # Signal the thread to stop (best-effort)
    job["status"] = "stopping"
    job["log"].append("Stop requested by user")

    return {"status": "stopping", "job_id": job_id}
