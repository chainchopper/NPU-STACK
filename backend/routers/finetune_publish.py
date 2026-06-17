"""Fine-Tuning & Publishing Router — Unsloth QLoRA + HuggingFace Hub.

Endpoints for:
  - Unsloth ecosystem detection
  - Dataset preparation and preview
  - QLoRA fine-tuning jobs
  - Model export (GGUF, SafeTensors, LoRA)
  - HuggingFace Hub publishing (models, GGUF, datasets)
  - Model card generation
"""

import json
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Form, Body

router = APIRouter(prefix="/api/finetune", tags=["fine-tuning"])

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAIN_PYTHON = REPO_ROOT / ".venv-train" / "Scripts" / "python.exe"

_jobs: dict = {}
_jobs_lock = threading.Lock()


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Poll training job status."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.get("/jobs")
def list_jobs():
    """List all training jobs."""
    with _jobs_lock:
        return {"jobs": list(_jobs.values()), "count": len(_jobs)}


# ── Ecosystem Status ────────────────────────────────────

@router.get("/status")
def finetune_status():
    """Get Unsloth and HF Hub ecosystem status."""
    from services.unsloth_service import detect_unsloth
    from services.hub_publisher import detect_hub
    return {
        "unsloth": detect_unsloth(),
        "hub": detect_hub(),
    }


# ── Dataset Preparation ─────────────────────────────────

@router.post("/dataset/prepare")
def prepare_dataset(
    source: str = Form(...),
    format: str = Form("auto"),
    max_samples: Optional[int] = Form(None),
    text_column: str = Form("text"),
    prompt_template: Optional[str] = Form(None),
):
    """Prepare and preview a dataset for fine-tuning."""
    from services.unsloth_service import prepare_dataset as prep
    result = prep(source, format, max_samples, text_column, prompt_template)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Dataset preparation failed"))
    return result


# ── Fine-Tuning ─────────────────────────────────────────

@router.post("/train")
async def start_training(
    model_name: str = Form("unsloth/tinyllama-bnb-4bit"),
    dataset_source: str = Form("..."),
    output_name: str = Form("finetuned-model"),
    num_epochs: int = Form(1),
    learning_rate: float = Form(2e-4),
    lora_r: int = Form(16),
    lora_alpha: int = Form(16),
    max_seq_length: int = Form(2048),
    per_device_batch_size: int = Form(2),
    gradient_accumulation_steps: int = Form(4),
    use_4bit: bool = Form(True),
):
    """Start QLoRA training in .venv-train subprocess. Agent-friendly."""
    if not TRAIN_PYTHON.exists():
        raise HTTPException(400, ".venv-train not found. Run: uv venv --python 3.12 .venv-train")

    # Resolve dataset path
    dataset_path = Path(dataset_source)
    if not dataset_path.exists():
        raise HTTPException(400, f"Dataset not found: {dataset_source}")

    job_id = f"train-{uuid.uuid4().hex[:8]}"
    output_dir = REPO_ROOT / "backend" / "data" / "finetune" / output_name

    script = (REPO_ROOT / "backend" / "services" / "run_finetune.py")
    # Normalize paths — Windows backslashes break Python f-strings in generated code
    safe_dataset = dataset_source.replace("\\", "/")
    safe_output = str(output_dir).replace("\\", "/")
    script.write_text(f'''# -*- coding: utf-8 -*-
"""NPU-STACK training script — auto-generated."""
import sys, json, os
os.environ["PYTHONWARNINGS"] = "ignore"

print("JOB_ID: {job_id}", flush=True)
print(f"Model: {model_name}", flush=True)
print(f"Dataset: {safe_dataset}", flush=True)
print(f"Epochs: {num_epochs}, LR: {learning_rate}, LoRA r={lora_r}", flush=True)
print("=" * 60, flush=True)

try:
    from unsloth import FastLanguageModel
    import torch
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments

    print(f"torch: {{torch.__version__}}, CUDA: {{torch.cuda.is_available()}}", flush=True)
    print(f"VRAM: {{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}} GB", flush=True)

    # Load model
    print(f"Loading {{model_name}}...", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="{model_name}",
        max_seq_length={max_seq_length},
        dtype=None,
        load_in_4bit={"True" if use_4bit else "False"},
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r={lora_r},
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha={lora_alpha},
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Load dataset
    print(f"Loading dataset...", flush=True)
    dataset = load_dataset("json", data_files=r"{safe_dataset}", split="train")
    print(f"Dataset: {{len(dataset)}} samples", flush=True)

    tokenizer.pad_token = tokenizer.eos_token

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length={max_seq_length},
        args=TrainingArguments(
            per_device_train_batch_size={per_device_batch_size},
            gradient_accumulation_steps={gradient_accumulation_steps},
            warmup_steps=5,
            num_train_epochs={num_epochs},
            learning_rate={learning_rate},
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=str(Path(r"{safe_output}")),
        ),
    )

    print("Starting training...", flush=True)
    trainer.train()

    print("Saving model...", flush=True)
    model.save_pretrained(str(Path(r"{safe_output}")))
    tokenizer.save_pretrained(str(Path(r"{safe_output}")))
    print("COMPLETE", flush=True)

except Exception as e:
    print(f"ERROR: {{e}}", flush=True)
    sys.exit(1)
''', encoding="utf-8")

    with _jobs_lock:
        _jobs[job_id] = {"status": "starting", "model": model_name, "dataset": dataset_source, "epochs": num_epochs, "output": output_name}

    def _run():
        try:
            result = subprocess.run(
                [str(TRAIN_PYTHON), "-u", str(script)],
                capture_output=True, text=True, timeout=3600, cwd=str(REPO_ROOT),
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            with _jobs_lock:
                # Success if stdout contains "COMPLETE" regardless of warnings in stderr
                if "COMPLETE" in stdout:
                    _jobs[job_id]["status"] = "complete"
                    _jobs[job_id]["output_lines"] = stdout.splitlines()[-10:]
                else:
                    _jobs[job_id]["status"] = "failed"
                    _jobs[job_id]["error"] = (
                        "".join(stderr.splitlines()[-5:]) if stderr else ""
                    ) + "\n" + (
                        "".join(stdout.splitlines()[-5:])
                    )
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(e)
        finally:
            try: script.unlink()
            except Exception: pass

    threading.Thread(target=_run, daemon=True).start()

    return {
        "job_id": job_id,
        "status": "starting",
        "model": model_name,
        "dataset": dataset_source,
        "output_name": output_name,
        "python": str(TRAIN_PYTHON),
        "action": f"curl http://127.0.0.1:8010/api/finetune/jobs/{job_id} to check status",
    }


# ── Export ──────────────────────────────────────────────

@router.post("/export")
def export_model(
    model_dir: Optional[str] = Form(None),
    export_format: str = Form("gguf"),
    quant_type: str = Form("q4_k_m"),
    merge_adapter: bool = Form(True),
):
    """Export a fine-tuned model to GGUF, SafeTensors, or LoRA format."""
    from services.unsloth_service import export_model as do_export
    if not model_dir:
        model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "finetune")
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "exports")
    result = do_export(model_dir, output_dir, export_format, quant_type, merge_adapter)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Export failed"))
    return result


# ── Model Card ──────────────────────────────────────────

@router.post("/model-card")
def create_model_card(
    model_name: str = Form(...),
    base_model: str = Form(...),
    task: str = Form("text-generation"),
    language: str = Form("en"),
    license: str = Form("apache-2.0"),
    description: str = Form(""),
    framework: str = Form("Unsloth + PEFT"),
):
    """Generate a HuggingFace model card."""
    from services.hub_publisher import generate_model_card
    card = generate_model_card(
        model_name=model_name,
        base_model=base_model,
        task=task,
        language=language,
        license=license,
        description=description,
        framework=framework,
    )
    return {"model_card": card}


# ── Publishing ──────────────────────────────────────────

@router.post("/publish/model")
def publish_model(
    model_dir: str = Form(...),
    repo_id: str = Form(...),
    private: bool = Form(False),
    commit_message: str = Form("Upload model via NPU-STACK"),
    generate_card: bool = Form(True),
    base_model: Optional[str] = Form(None),
):
    """Push a model directory to HuggingFace Hub."""
    from services.hub_publisher import push_model_to_hub, generate_model_card

    model_card = None
    if generate_card and base_model:
        model_card = generate_model_card(
            model_name=repo_id.split("/")[-1],
            base_model=base_model,
        )

    result = push_model_to_hub(model_dir, repo_id, private, commit_message, model_card)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Upload failed"))
    return result


@router.post("/publish/gguf")
def publish_gguf(
    gguf_path: str = Form(...),
    repo_id: str = Form(...),
    private: bool = Form(False),
    base_model: Optional[str] = Form(None),
):
    """Push a single GGUF file to HuggingFace Hub."""
    from services.hub_publisher import push_gguf_to_hub, generate_model_card

    model_card = None
    if base_model:
        model_card = generate_model_card(
            model_name=repo_id.split("/")[-1],
            base_model=base_model,
            task="text-generation",
        )

    result = push_gguf_to_hub(gguf_path, repo_id, private, model_card)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Upload failed"))
    return result


@router.post("/publish/dataset")
def publish_dataset(
    data_dir: str = Form(...),
    repo_id: str = Form(...),
    private: bool = Form(False),
):
    """Push a dataset directory to HuggingFace Hub."""
    from services.hub_publisher import push_dataset_to_hub
    result = push_dataset_to_hub(data_dir, repo_id, private)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Upload failed"))
    return result
