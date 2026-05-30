"""HuggingFace Hub Publisher — Push models, datasets, and model cards to HF Hub.

Provides:
  - Model card generation (metadata, training info, benchmarks)
  - Model upload to HuggingFace Hub (GGUF, SafeTensors, LoRA adapters)
  - Dataset upload
  - Repository management (create, update, tag)

Requires: huggingface_hub
"""

import os
import json
import time
from typing import Optional, List, Dict


# ── Detection ───────────────────────────────────────────

def detect_hub() -> dict:
    """Detect HuggingFace Hub availability and authentication status."""
    info = {
        "hub_available": False,
        "hub_version": None,
        "authenticated": False,
        "username": None,
        "token_set": False,
    }

    try:
        import huggingface_hub
        info["hub_available"] = True
        info["hub_version"] = huggingface_hub.__version__

        # Check authentication
        try:
            user_info = huggingface_hub.whoami()
            info["authenticated"] = True
            info["username"] = user_info.get("name", "")
        except Exception:
            pass

        # Check token (support old and new huggingface_hub APIs)
        token = None
        try:
            # Newer versions expose get_token at module level
            token = huggingface_hub.get_token()
        except Exception:
            try:
                # Older versions exposed HfFolder.get_token
                HfFolder = getattr(huggingface_hub, "HfFolder", None)
                if HfFolder and hasattr(HfFolder, "get_token"):
                    token = HfFolder.get_token()
            except Exception:
                token = None

        info["token_set"] = token is not None

    except ImportError:
        pass

    return info


# ── Model Card Generation ──────────────────────────────

def generate_model_card(
    model_name: str,
    base_model: str,
    task: str = "text-generation",
    language: str = "en",
    license: str = "apache-2.0",
    description: str = "",
    training_info: Optional[Dict] = None,
    tags: Optional[List[str]] = None,
    datasets_used: Optional[List[str]] = None,
    metrics: Optional[Dict] = None,
    framework: str = "Unsloth + PEFT",
) -> str:
    """Generate a README.md model card in HuggingFace format.

    Args:
        model_name: Display name of the model
        base_model: Base model name (e.g., "meta-llama/Llama-3.2-1B")
        task: Task type (text-generation, text-classification, etc.)
        language: Language code
        license: License identifier
        description: Model description
        training_info: Training hyperparameters and results
        tags: Additional tags
        datasets_used: Datasets used for training
        metrics: Evaluation metrics
        framework: Framework used for training

    Returns:
        Model card content as a string
    """
    # Build YAML frontmatter
    yaml_parts = [
        "---",
        f'language: {language}',
        f'license: {license}',
        f'base_model: {base_model}',
    ]

    all_tags = ["fine-tuned", framework.lower().replace(" ", "-")]
    if tags:
        all_tags.extend(tags)
    yaml_parts.append(f'tags: {json.dumps(all_tags)}')

    if datasets_used:
        yaml_parts.append(f'datasets: {json.dumps(datasets_used)}')

    yaml_parts.append(f'pipeline_tag: {task}')
    yaml_parts.append("---")

    # Build markdown body
    body_parts = [
        f"# {model_name}",
        "",
        description or f"Fine-tuned version of [{base_model}](https://huggingface.co/{base_model}) using {framework}.",
        "",
    ]

    # Model details
    body_parts.extend([
        "## Model Details",
        "",
        f"- **Base Model:** [{base_model}](https://huggingface.co/{base_model})",
        f"- **Task:** {task}",
        f"- **Framework:** {framework}",
        f"- **License:** {license}",
        "",
    ])

    # Training info
    if training_info:
        body_parts.extend([
            "## Training",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
        ])
        for k, v in training_info.items():
            body_parts.append(f"| {k} | {v} |")
        body_parts.append("")

    # Metrics
    if metrics:
        body_parts.extend([
            "## Evaluation",
            "",
            "| Metric | Value |",
            "|--------|-------|",
        ])
        for k, v in metrics.items():
            body_parts.append(f"| {k} | {v} |")
        body_parts.append("")

    # Usage
    body_parts.extend([
        "## Usage",
        "",
        "```python",
        "from transformers import AutoModelForCausalLM, AutoTokenizer",
        "",
        f'model = AutoModelForCausalLM.from_pretrained("{model_name}")',
        f'tokenizer = AutoTokenizer.from_pretrained("{model_name}")',
        "",
        'inputs = tokenizer("Hello, how are you?", return_tensors="pt")',
        "outputs = model.generate(**inputs, max_new_tokens=100)",
        "print(tokenizer.decode(outputs[0], skip_special_tokens=True))",
        "```",
        "",
        "## Built With",
        "",
        "- [NPU-STACK](https://github.com/chainchopper/NPU-STACK) — AI Model Factory",
        f"- [{framework}](https://github.com/unslothai/unsloth)",
        "",
    ])

    return "\n".join(yaml_parts) + "\n\n" + "\n".join(body_parts)


# ── Upload to HuggingFace Hub ───────────────────────────

def push_model_to_hub(
    model_dir: str,
    repo_id: str,
    private: bool = False,
    commit_message: str = "Upload model via NPU-STACK",
    model_card: Optional[str] = None,
    create_repo: bool = True,
) -> dict:
    """Push a model directory to HuggingFace Hub.

    Args:
        model_dir: Local directory containing model files
        repo_id: HuggingFace repo ID (e.g., "username/model-name")
        private: Whether the repo should be private
        commit_message: Commit message for the upload
        model_card: Model card content (if None, uses existing README.md)
        create_repo: Create the repo if it doesn't exist

    Returns:
        Dict with repo URL and upload info
    """
    try:
        from huggingface_hub import HfApi, create_repo as hf_create_repo
    except ImportError:
        return {"success": False, "error": "huggingface_hub not installed: pip install huggingface_hub"}

    if not os.path.isdir(model_dir):
        return {"success": False, "error": f"Model directory not found: {model_dir}"}

    api = HfApi()

    try:
        # Create repo if needed
        if create_repo:
            try:
                hf_create_repo(repo_id, private=private, repo_type="model", exist_ok=True)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    return {"success": False, "error": f"Failed to create repo: {e}"}

        # Write model card if provided
        if model_card:
            readme_path = os.path.join(model_dir, "README.md")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(model_card)

        # Upload all files
        start_time = time.time()
        api.upload_folder(
            folder_path=model_dir,
            repo_id=repo_id,
            repo_type="model",
            commit_message=commit_message,
        )
        elapsed = time.time() - start_time

        # Count uploaded files
        files = []
        for root, dirs, filenames in os.walk(model_dir):
            for fn in filenames:
                fp = os.path.join(root, fn)
                files.append({
                    "name": os.path.relpath(fp, model_dir),
                    "size": os.path.getsize(fp),
                })

        return {
            "success": True,
            "repo_id": repo_id,
            "url": f"https://huggingface.co/{repo_id}",
            "private": private,
            "files_uploaded": len(files),
            "total_size": sum(f["size"] for f in files),
            "elapsed_seconds": round(elapsed, 1),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def push_gguf_to_hub(
    gguf_path: str,
    repo_id: str,
    private: bool = False,
    model_card: Optional[str] = None,
) -> dict:
    """Push a single GGUF file to HuggingFace Hub.

    Args:
        gguf_path: Path to the .gguf file
        repo_id: HuggingFace repo ID
        private: Whether the repo should be private
        model_card: Model card content

    Returns:
        Dict with upload result
    """
    try:
        from huggingface_hub import HfApi, create_repo as hf_create_repo
    except ImportError:
        return {"success": False, "error": "huggingface_hub not installed: pip install huggingface_hub"}

    if not os.path.isfile(gguf_path):
        return {"success": False, "error": f"GGUF file not found: {gguf_path}"}

    api = HfApi()

    try:
        # Create repo
        try:
            hf_create_repo(repo_id, private=private, repo_type="model", exist_ok=True)
        except Exception as e:
            if "already exists" not in str(e).lower():
                return {"success": False, "error": f"Failed to create repo: {e}"}

        # Upload model card first
        if model_card:
            api.upload_file(
                path_or_fileobj=model_card.encode("utf-8"),
                path_in_repo="README.md",
                repo_id=repo_id,
                repo_type="model",
            )

        # Upload GGUF file
        start_time = time.time()
        api.upload_file(
            path_or_fileobj=gguf_path,
            path_in_repo=os.path.basename(gguf_path),
            repo_id=repo_id,
            repo_type="model",
        )
        elapsed = time.time() - start_time

        return {
            "success": True,
            "repo_id": repo_id,
            "url": f"https://huggingface.co/{repo_id}",
            "file": os.path.basename(gguf_path),
            "file_size": os.path.getsize(gguf_path),
            "elapsed_seconds": round(elapsed, 1),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def push_dataset_to_hub(
    data_dir: str,
    repo_id: str,
    private: bool = False,
    commit_message: str = "Upload dataset via NPU-STACK",
) -> dict:
    """Push a dataset directory to HuggingFace Hub.

    Args:
        data_dir: Local directory containing dataset files
        repo_id: HuggingFace repo ID
        private: Whether the repo should be private
        commit_message: Commit message

    Returns:
        Dict with upload result
    """
    try:
        from huggingface_hub import HfApi, create_repo as hf_create_repo
    except ImportError:
        return {"success": False, "error": "huggingface_hub not installed"}

    if not os.path.isdir(data_dir):
        return {"success": False, "error": f"Dataset directory not found: {data_dir}"}

    api = HfApi()

    try:
        try:
            hf_create_repo(repo_id, private=private, repo_type="dataset", exist_ok=True)
        except Exception as e:
            if "already exists" not in str(e).lower():
                return {"success": False, "error": f"Failed to create repo: {e}"}

        start_time = time.time()
        api.upload_folder(
            folder_path=data_dir,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=commit_message,
        )
        elapsed = time.time() - start_time

        return {
            "success": True,
            "repo_id": repo_id,
            "url": f"https://huggingface.co/datasets/{repo_id}",
            "private": private,
            "elapsed_seconds": round(elapsed, 1),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
