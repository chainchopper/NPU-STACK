"""Fine-Tuning & Publishing Router — Unsloth QLoRA + HuggingFace Hub.

Endpoints for:
  - Unsloth ecosystem detection
  - Dataset preparation and preview
  - QLoRA fine-tuning jobs
  - Model export (GGUF, SafeTensors, LoRA)
  - HuggingFace Hub publishing (models, GGUF, datasets)
  - Model card generation
"""

import os
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Form

router = APIRouter(prefix="/api/finetune", tags=["fine-tuning"])


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
def start_training(
    model_name: str = Form(...),
    dataset_source: str = Form(...),
    max_seq_length: int = Form(2048),
    num_epochs: int = Form(1),
    learning_rate: float = Form(2e-4),
    per_device_batch_size: int = Form(2),
    gradient_accumulation_steps: int = Form(4),
    warmup_steps: int = Form(5),
    lora_r: int = Form(16),
    lora_alpha: int = Form(16),
    lora_dropout: float = Form(0.0),
    dataset_format: str = Form("auto"),
    text_column: str = Form("text"),
    prompt_template: Optional[str] = Form(None),
    max_samples: Optional[int] = Form(None),
    use_4bit: bool = Form(True),
):
    """Start a QLoRA fine-tuning job with Unsloth."""
    from services.unsloth_service import start_finetuning
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "finetune")
    result = start_finetuning(
        model_name=model_name,
        dataset_source=dataset_source,
        output_dir=output_dir,
        max_seq_length=max_seq_length,
        num_epochs=num_epochs,
        learning_rate=learning_rate,
        per_device_batch_size=per_device_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        warmup_steps=warmup_steps,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        dataset_format=dataset_format,
        text_column=text_column,
        prompt_template=prompt_template,
        max_samples=max_samples,
        use_4bit=use_4bit,
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Training failed"))
    return result


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
