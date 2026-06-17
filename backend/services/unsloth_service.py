"""Unsloth Fine-Tuning Service — Fast QLoRA/LoRA fine-tuning for LLMs.

Wraps the Unsloth library for:
  - 4-bit QLoRA fine-tuning (2-4x faster, 70% less VRAM)
  - Supported models: Llama 3, Mistral, Phi-3, Gemma, Qwen, DeepSeek
  - Export to GGUF, SafeTensors, LoRA adapters
  - Dataset loading from HuggingFace, JSON/JSONL, CSV
  - Training progress tracking

Gracefully degrades when dependencies are not installed.
"""

import os
import subprocess
import time
from pathlib import Path
import json
from typing import Optional, Dict, List


# ── Detection ───────────────────────────────────────────

def detect_unsloth() -> dict:
    """Detect Unsloth ecosystem and dependencies."""
    info = {
        "unsloth_available": False,
        "unsloth_version": None,
        "torch_available": False,
        "torch_version": None,
        "cuda_available": False,
        "cuda_version": None,
        "accelerated_available": False,
        "fallback_available": False,
        "peft_available": False,
        "transformers_available": False,
        "trl_available": False,
        "bitsandbytes_available": False,
        "supported_models": [],
        "gpu_info": None,
    }

    # PyTorch + CUDA
    try:
        import torch
        info["torch_available"] = True
        info["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            info["cuda_available"] = True
            info["cuda_version"] = torch.version.cuda
            info["gpu_info"] = {
                "name": torch.cuda.get_device_name(0),
                "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1),
                "compute_capability": f"{torch.cuda.get_device_properties(0).major}.{torch.cuda.get_device_properties(0).minor}",
            }
    except ImportError:
        pass

    # Unsloth (may crash on Python 3.14 even if installed)
    try:
        import unsloth
        info["unsloth_available"] = True
        info["unsloth_version"] = getattr(unsloth, "__version__", "installed")
    except Exception:
        pass

    # Supporting libraries (each in its own try — transformers may crash on 3.14 too)
    try:
        import peft  # noqa: F401
        info["peft_available"] = True
    except Exception:
        pass

    try:
        import transformers  # noqa: F401
        info["transformers_available"] = True
    except Exception:
        pass

    try:
        import trl  # noqa: F401
        info["trl_available"] = True
    except Exception:
        pass

    try:
        import bitsandbytes  # noqa: F401
        info["bitsandbytes_available"] = True
    except Exception:
        pass

    # Supported model families
    info["supported_models"] = [
        "unsloth/llama-3.2-1b-bnb-4bit",
        "unsloth/llama-3.2-3b-bnb-4bit",
        "unsloth/llama-3.1-8b-bnb-4bit",
        "unsloth/mistral-7b-v0.3-bnb-4bit",
        "unsloth/Phi-3.5-mini-instruct-bnb-4bit",
        "unsloth/gemma-2-2b-it-bnb-4bit",
        "unsloth/gemma-2-9b-it-bnb-4bit",
        "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
        "unsloth/DeepSeek-R1-Distill-Qwen-7B-bnb-4bit",
        "unsloth/tinyllama-bnb-4bit",
    ]

    info["fallback_available"] = all([
        info["unsloth_available"],
        info["torch_available"],
        info["peft_available"],
        info["transformers_available"],
        info["trl_available"],
    ])
    info["accelerated_available"] = all([
        info["fallback_available"],
        info["cuda_available"],
    ])
    info["ready"] = info["fallback_available"]
    if info["accelerated_available"]:
        info["best_mode"] = "cuda-accelerated"
        info["recommendation"] = "Full Unsloth stack ready. Training will use CUDA acceleration (2-4x faster, 70% less VRAM)."
    elif info["fallback_available"]:
        info["best_mode"] = "cpu-fallback"
        info["recommendation"] = "Unsloth is available in CPU fallback mode. Training will work but will be slow. Install CUDA + bitsandbytes for acceleration."
    else:
        info["best_mode"] = "missing-dependencies"
        missing_libs = [k for k in ["unsloth", "peft", "transformers", "trl"] if not info[f"{k}_available"]]
        info["recommendation"] = f"Missing dependencies: {', '.join(missing_libs)}. Use the install command on this page."

    # Training venv detection
    info["training_venv"] = _detect_training_venv()

    return info


def _detect_training_venv() -> dict:
    """Detect dedicated .venv-train (Python 3.12) for Unsloth training."""
    repo_root = Path(__file__).resolve().parents[2]
    train_dir = Path(os.getenv("NPU_TRAIN_VENV", str(repo_root / ".venv-train")))
    if not train_dir.exists():
        return {"available": False, "message": ".venv-train not found"}
    python_exe = train_dir / "Scripts" / "python.exe" if os.name == "nt" else train_dir / "bin" / "python"
    if not python_exe.exists():
        return {"available": False, "path": str(train_dir)}
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import torch; print(torch.__version__); print(torch.cuda.is_available())"],
            capture_output=True, text=True, timeout=30,
        )
        lines = (result.stdout or "").strip().splitlines()
        return {
            "available": True, "path": str(train_dir), "python": str(python_exe),
            "torch_version": lines[0] if lines else "?", "cuda": lines[1] == "True" if len(lines) > 1 else False,
            "ready": bool(lines and len(lines) > 1 and lines[1] == "True"),
        }
    except Exception as e:
        return {"available": True, "path": str(train_dir), "error": str(e)}


# ── Dataset Preparation ─────────────────────────────────

def prepare_dataset(
    source: str,
    format: str = "auto",
    max_samples: Optional[int] = None,
    text_column: str = "text",
    prompt_template: Optional[str] = None,
) -> dict:
    """Prepare a dataset for fine-tuning.

    Args:
        source: HuggingFace dataset name, or path to JSON/JSONL/CSV
        format: "auto", "huggingface", "json", "jsonl", "csv"
        max_samples: Maximum number of samples to use
        text_column: Column name containing the text data
        prompt_template: Optional Alpaca/ChatML prompt template

    Returns:
        Dict with dataset info and sample count
    """
    try:
        from datasets import load_dataset
    except ImportError:
        return {"success": False, "error": "datasets not installed: pip install datasets"}

    try:
        # Detect format
        if format == "auto":
            if os.path.isfile(source):
                ext = os.path.splitext(source)[1].lower()
                format = {"json": "json", ".jsonl": "json", ".csv": "csv"}.get(ext, "json")
            else:
                format = "huggingface"

        # Load dataset
        if format == "huggingface":
            dataset = load_dataset(source, split="train")
        elif format in ("json", "jsonl"):
            dataset = load_dataset("json", data_files=source, split="train")
        elif format == "csv":
            dataset = load_dataset("csv", data_files=source, split="train")
        else:
            return {"success": False, "error": f"Unknown format: {format}"}

        # Limit samples
        if max_samples and len(dataset) > max_samples:
            dataset = dataset.select(range(max_samples))

        # Apply prompt template if provided
        formatted = False
        if prompt_template:
            # Standard Alpaca template
            if prompt_template == "alpaca":
                def format_alpaca(row):
                    instruction = row.get("instruction", "")
                    inp = row.get("input", "")
                    output = row.get("output", "")
                    if inp:
                        text = f"### Instruction:\n{instruction}\n\n### Input:\n{inp}\n\n### Response:\n{output}"
                    else:
                        text = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"
                    return {"text": text}
                dataset = dataset.map(format_alpaca)
                formatted = True

            # ChatML template
            elif prompt_template == "chatml":
                def format_chatml(row):
                    messages = row.get("messages", [])
                    if not messages:
                        return {"text": row.get(text_column, "")}
                    text = ""
                    for msg in messages:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        text += f"<|im_start|>{role}\n{content}<|im_end|>\n"
                    return {"text": text}
                dataset = dataset.map(format_chatml)
                formatted = True

        return {
            "success": True,
            "source": source,
            "format": format,
            "num_samples": len(dataset),
            "columns": dataset.column_names,
            "formatted": formatted,
            "prompt_template": prompt_template,
            "sample_preview": str(dataset[0]) if len(dataset) > 0 else None,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Fine-Tuning ─────────────────────────────────────────

def start_finetuning(
    model_name: str,
    dataset_source: str,
    output_dir: str,
    # Training hyperparameters
    max_seq_length: int = 2048,
    num_epochs: int = 1,
    learning_rate: float = 2e-4,
    per_device_batch_size: int = 2,
    gradient_accumulation_steps: int = 4,
    warmup_steps: int = 5,
    # LoRA config
    lora_r: int = 16,
    lora_alpha: int = 16,
    lora_dropout: float = 0.0,
    # Dataset
    dataset_format: str = "auto",
    text_column: str = "text",
    prompt_template: Optional[str] = None,
    max_samples: Optional[int] = None,
    # Options
    use_4bit: bool = True,
    save_steps: int = 100,
    logging_steps: int = 10,
) -> dict:
    """Start a fine-tuning job using Unsloth.

    Args:
        model_name: HuggingFace model name or Unsloth 4-bit model
        dataset_source: HuggingFace dataset name or file path
        output_dir: Directory for saving the fine-tuned model
        max_seq_length: Maximum sequence length
        num_epochs: Number of training epochs
        learning_rate: Learning rate
        per_device_batch_size: Batch size per device
        gradient_accumulation_steps: Gradient accumulation steps
        warmup_steps: Warmup steps
        lora_r: LoRA rank (4, 8, 16, 32, 64)
        lora_alpha: LoRA alpha
        lora_dropout: LoRA dropout
        dataset_format: Dataset format
        text_column: Text column name
        prompt_template: Prompt template (alpaca, chatml, None)
        max_samples: Max training samples
        use_4bit: Use 4-bit quantization
        save_steps: Save checkpoint every N steps
        logging_steps: Log every N steps

    Returns:
        Dict with training results
    """
    # Validate environment
    env = detect_unsloth()
    if not env["unsloth_available"]:
        return {
            "success": False,
            "error": "Unsloth not installed. Install: pip install unsloth",
            "install": "pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'",
        }

    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError as e:
        return {"success": False, "error": f"Missing dependency: {e}"}

    os.makedirs(output_dir, exist_ok=True)

    try:
        start_time = time.time()

        # On CPU / fallback paths, keep the configuration conservative and portable.
        if not env["cuda_available"]:
            use_4bit = False

        # 1. Load model with Unsloth acceleration
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_name,
            max_seq_length=max_seq_length,
            dtype=None if env["cuda_available"] else None,
            load_in_4bit=use_4bit,
        )

        # 2. Apply LoRA adapters
        model = FastLanguageModel.get_peft_model(
            model,
            r=lora_r,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            bias="none",
            use_gradient_checkpointing="unsloth",
        )

        # 3. Load and prepare dataset
        if os.path.isfile(dataset_source):
            ext = os.path.splitext(dataset_source)[1].lower()
            ds_format = {"json": "json", ".jsonl": "json", ".csv": "csv"}.get(ext, "json")
            dataset = load_dataset(ds_format, data_files=dataset_source, split="train")
        else:
            dataset = load_dataset(dataset_source, split="train")

        if max_samples and len(dataset) > max_samples:
            dataset = dataset.select(range(max_samples))

        # 4. Format dataset if template provided
        if prompt_template == "alpaca":
            def format_alpaca(row):
                instruction = row.get("instruction", "")
                inp = row.get("input", "")
                output = row.get("output", "")
                if inp:
                    return {"text": f"### Instruction:\n{instruction}\n\n### Input:\n{inp}\n\n### Response:\n{output}"}
                return {"text": f"### Instruction:\n{instruction}\n\n### Response:\n{output}"}
            dataset = dataset.map(format_alpaca)
            text_column = "text"

        # 5. Create trainer
        training_args = TrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=per_device_batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            warmup_steps=warmup_steps,
            num_train_epochs=num_epochs,
            learning_rate=learning_rate,
            fp16=bool(env["cuda_available"]),
            logging_steps=logging_steps,
            save_steps=save_steps,
            optim="adamw_8bit" if env["cuda_available"] else "adamw_torch",
            seed=42,
            report_to="none",
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            dataset_text_field=text_column,
            max_seq_length=max_seq_length,
            args=training_args,
        )

        # 6. Train
        train_result = trainer.train()
        elapsed = time.time() - start_time

        # 7. Save model
        model.save_pretrained(os.path.join(output_dir, "lora_adapter"))
        tokenizer.save_pretrained(os.path.join(output_dir, "lora_adapter"))

        # Training metrics
        metrics = train_result.metrics if hasattr(train_result, "metrics") else {}

        return {
            "success": True,
            "model_name": model_name,
            "dataset": dataset_source,
            "output_dir": output_dir,
            "adapter_path": os.path.join(output_dir, "lora_adapter"),
            "training_samples": len(dataset),
            "epochs": num_epochs,
            "lora_rank": lora_r,
            "elapsed_seconds": round(elapsed, 1),
            "metrics": {
                "train_loss": metrics.get("train_loss"),
                "train_runtime": metrics.get("train_runtime"),
                "train_samples_per_second": metrics.get("train_samples_per_second"),
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Export ──────────────────────────────────────────────

def export_model(
    model_dir: str,
    output_dir: str,
    export_format: str = "gguf",
    quant_type: str = "q4_k_m",
    merge_adapter: bool = True,
) -> dict:
    """Export a fine-tuned model to various formats.

    Args:
        model_dir: Path to the Unsloth output directory (with lora_adapter/)
        output_dir: Directory for the exported model
        export_format: "gguf", "safetensors", "lora_only", "merged_16bit"
        quant_type: GGUF quantization type
        merge_adapter: Whether to merge LoRA weights into base model

    Returns:
        Dict with exported model path
    """
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        return {"success": False, "error": "Unsloth not installed"}

    adapter_path = os.path.join(model_dir, "lora_adapter")
    if not os.path.isdir(adapter_path):
        return {"success": False, "error": f"LoRA adapter not found at {adapter_path}"}

    os.makedirs(output_dir, exist_ok=True)

    try:
        # Load the fine-tuned model
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=adapter_path,
            max_seq_length=2048,
            dtype=None,
            load_in_4bit=True,
        )

        if export_format == "gguf":
            # Export to GGUF with quantization
            model.save_pretrained_gguf(
                output_dir,
                tokenizer,
                quantization_method=quant_type,
            )
            # Find generated GGUF file
            gguf_files = [f for f in os.listdir(output_dir) if f.endswith(".gguf")]
            return {
                "success": True,
                "format": "gguf",
                "quant_type": quant_type,
                "output_files": [os.path.join(output_dir, f) for f in gguf_files],
            }

        elif export_format == "safetensors":
            # Export merged model in SafeTensors format
            if merge_adapter:
                model.save_pretrained_merged(
                    output_dir,
                    tokenizer,
                    save_method="merged_16bit",
                )
            else:
                model.save_pretrained(output_dir)
                tokenizer.save_pretrained(output_dir)
            return {
                "success": True,
                "format": "safetensors",
                "merged": merge_adapter,
                "output_dir": output_dir,
            }

        elif export_format == "lora_only":
            # Save just the LoRA adapter
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)
            return {
                "success": True,
                "format": "lora_adapter",
                "output_dir": output_dir,
            }

        elif export_format == "merged_16bit":
            model.save_pretrained_merged(
                output_dir,
                tokenizer,
                save_method="merged_16bit",
            )
            return {
                "success": True,
                "format": "merged_16bit",
                "output_dir": output_dir,
            }

        else:
            return {"success": False, "error": f"Unknown export format: {export_format}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
