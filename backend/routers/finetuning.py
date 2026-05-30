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
import threading
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException, Form, Depends
from sqlalchemy.orm import Session

from database import get_db, SessionLocal, ModelRecord, FinetuneJob

router = APIRouter(prefix="/api/finetune", tags=["fine-tuning"])

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets")
MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(DATASET_DIR, exist_ok=True)

# Runtime helpers for active worker threads (state itself is persisted in DB)
_job_threads: Dict[int, threading.Thread] = {}
_job_stop_flags: Dict[int, bool] = {}


def _utcnow():
    return datetime.now(timezone.utc)


def _append_job_log(db, job: FinetuneJob, message: str):
    history = list(job.log_history or [])
    history.append(message)
    job.log_history = history[-250:]
    db.commit()


def _append_job_metric(db, job: FinetuneJob, metric: dict):
    history = list(job.metrics_history or [])
    history.append(metric)
    job.metrics_history = history[-500:]
    db.commit()


def _run_finetune_job(job_id: int, config: dict):
    """Background fine-tuning worker using PEFT/LoRA."""
    db = SessionLocal()
    job = db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
    if not job:
        db.close()
        return

    job.status = "running"
    job.started_at = _utcnow()
    db.commit()

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
            DataCollatorForLanguageModeling,
        )

        _append_job_log(db, job, "Loading base model...")
        model_path = config["model_path"]
        model_dir = model_path if os.path.isdir(model_path) else os.path.dirname(model_path)

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
                _append_job_log(db, job, f"LoRA applied: r={lora_config.r}, alpha={lora_config.lora_alpha}")
                trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
                total = sum(p.numel() for p in model.parameters())
                _append_job_log(db, job, f"Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.1f}%)")
            except ImportError:
                _append_job_log(db, job, "peft not installed — training full model (pip install peft for LoRA)")
                use_lora = False

        # Load dataset
        _append_job_log(db, job, f"Loading dataset: {config['dataset_path']}")
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
        _append_job_log(db, job, f"Dataset tokenized: {len(tokenized_dataset)} examples")

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
        from transformers import TrainerCallback

        class MetricsCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs:
                    metric = {
                        "step": state.global_step,
                        "epoch": round(state.epoch, 2) if state.epoch else 0,
                        "loss": logs.get("loss"),
                        "learning_rate": logs.get("learning_rate"),
                    }
                    live_job = db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
                    if live_job:
                        live_job.current_step = state.global_step
                        live_job.current_epoch = round(state.epoch, 2) if state.epoch else 0
                        db.commit()
                        _append_job_metric(db, live_job, metric)

            def on_step_end(self, args, state, control, **kwargs):
                if _job_stop_flags.get(job_id, False):
                    control.should_training_stop = True
                return control

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset,
            data_collator=data_collator,
            callbacks=[MetricsCallback()],
        )

        _append_job_log(db, job, "Training started...")
        trainer.train()

        if _job_stop_flags.get(job_id, False):
            job.status = "stopped"
            job.completed_at = _utcnow()
            _append_job_log(db, job, "Training stopped by user")
            db.commit()
            return

        # Save the model
        _append_job_log(db, job, "Saving fine-tuned model...")
        if use_lora:
            model.save_pretrained(output_dir)
        else:
            model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

        # Register resulting model directory
        created_model = ModelRecord(
            name=f"{job.model_name} (Fine-Tuned)",
            framework="transformers",
            format="directory",
            file_path=output_dir,
            file_size=0,
            description=f"Fine-tuned artifact from job {job.id}",
            metadata_json={"finetune_job_id": job.id},
        )
        db.add(created_model)
        db.commit()
        db.refresh(created_model)

        job.status = "completed"
        job.completed_at = _utcnow()
        job.output_dir = output_dir
        job.resulting_model_id = created_model.id
        _append_job_log(db, job, f"Fine-tuning complete! Model saved to {output_dir}")
        db.commit()

    except Exception as e:
        live_job = db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
        if live_job:
            live_job.status = "failed"
            live_job.error_message = str(e)
            live_job.completed_at = _utcnow()
            _append_job_log(db, live_job, f"Error: {str(e)}")
            db.commit()
    finally:
        _job_stop_flags.pop(job_id, None)
        db.close()


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

    config_payload = {
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "use_lora": use_lora,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "text_column": text_column,
        "max_length": max_length,
    }

    job = FinetuneJob(
        model_id=model_id,
        model_name=record.name,
        dataset=dataset,
        dataset_path=dataset_path,
        status="initializing",
        config=config_payload,
        current_step=0,
        current_epoch=0,
        metrics_history=[],
        log_history=[],
        created_at=_utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    _append_job_log(db, job, "Fine-tune job created")
    _append_job_log(db, job, f"Base model: {record.name}")
    _append_job_log(db, job, f"Dataset path: {dataset_path}")

    config = {
        "model_path": record.file_path,
        "dataset_path": dataset_path,
        **config_payload,
    }

    _job_stop_flags[job.id] = False
    thread = threading.Thread(target=_run_finetune_job, args=(job.id, config), daemon=True)
    _job_threads[job.id] = thread
    thread.start()

    return {
        "job_id": job.id,
        "status": "initializing",
        "model": record.name,
        "dataset": dataset,
        "config": config_payload,
    }


@router.get("/jobs")
async def list_jobs():
    """List all fine-tuning jobs."""
    db = SessionLocal()
    rows = db.query(FinetuneJob).order_by(FinetuneJob.created_at.desc()).all()
    jobs = [
        {
            "id": job.id,
            "model_name": job.model_name,
            "dataset": job.dataset,
            "status": job.status,
            "created_at": job.created_at.timestamp() if job.created_at else None,
            "current_step": job.current_step,
            "current_epoch": job.current_epoch,
            "error": job.error_message,
        }
        for job in rows
    ]
    db.close()
    return {"jobs": jobs}


@router.get("/status/{job_id}")
async def get_job_status(job_id: int):
    """Get detailed status and metrics for a fine-tuning job."""
    db = SessionLocal()
    job = db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
    if not job:
        db.close()
        raise HTTPException(404, f"Job '{job_id}' not found")

    payload = {
        "id": job.id,
        "model_name": job.model_name,
        "dataset": job.dataset,
        "status": job.status,
        "created_at": job.created_at.timestamp() if job.created_at else None,
        "started_at": job.started_at.timestamp() if job.started_at else None,
        "completed_at": job.completed_at.timestamp() if job.completed_at else None,
        "current_step": job.current_step,
        "current_epoch": job.current_epoch,
        "config": job.config,
        "metrics": (job.metrics_history or [])[-50:],
        "log": (job.log_history or [])[-20:],
        "output_dir": job.output_dir,
        "resulting_model_id": job.resulting_model_id,
        "error": job.error_message,
    }
    db.close()
    return payload


@router.post("/stop/{job_id}")
async def stop_job(job_id: int):
    """Stop a running fine-tuning job."""
    db = SessionLocal()
    job = db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
    if not job:
        db.close()
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.status != "running":
        payload = {"status": job.status, "message": "Job is not running"}
        db.close()
        return payload

    # Signal the thread to stop (best-effort)
    _job_stop_flags[job_id] = True
    job.status = "stopping"
    _append_job_log(db, job, "Stop requested by user")
    db.commit()
    db.close()

    return {"status": "stopping", "job_id": job_id}
