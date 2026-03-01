"""System Agent Router — Built-in AI assistant powered by a local GGUF model.

Endpoints:
  GET  /api/agent/status           — Check if agent model is downloaded/running
  POST /api/agent/init             — Download the Phi-3-mini GGUF in background
  POST /api/agent/start            — Load the agent model into memory via gguf_service
  POST /api/agent/chat             — Chat with the loaded agent model directly
  POST /api/agent/generate-dataset — Generate npu_stack_knowledge.jsonl
"""

import os
import json
import shutil
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from database import SessionLocal, ModelRecord, get_db

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Constants from environment or defaults
AGENT_REPO_ID = "microsoft/Phi-3-mini-4k-instruct-gguf"
AGENT_MODEL_FILENAME = "Phi-3-mini-4k-instruct-q4.gguf"
DATASET_FILENAME = "npu_stack_knowledge.jsonl"

def _get_token():
    return os.getenv("HUGGINGFACE_TOKEN")

def _model_store():
    # Use the same MODEL_STORE as main.py/huggingface.py
    from main import MODEL_STORE
    return MODEL_STORE

def _model_path():
    return os.path.join(_model_store(), AGENT_MODEL_FILENAME)

def _dataset_path():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets", DATASET_FILENAME)


# ── Status ──────────────────────────────────────────────


class AgentState(BaseModel):
    is_downloaded: bool
    is_running: bool
    dataset_ready: bool


@router.get("/status", response_model=AgentState)
def get_agent_status():
    """Check if the system agent model is downloaded, loaded, and if the dataset exists."""
    from services.gguf_service import get_loaded_models

    loaded = get_loaded_models()
    model_path = _model_path()
    is_running = any(m.get("filename") == AGENT_MODEL_FILENAME for m in loaded)

    return AgentState(
        is_downloaded=os.path.exists(model_path),
        is_running=is_running,
        dataset_ready=os.path.exists(_dataset_path()),
    )


# ── Init (Download) ────────────────────────────────────


def _download_model_task():
    model_path = _model_path()
    model_store = _model_store()
    os.makedirs(model_store, exist_ok=True)

    if not os.path.exists(model_path):
        try:
            print(f"[Agent] Downloading {AGENT_MODEL_FILENAME} from {AGENT_REPO_ID} via HTTP streaming...")
            import requests
            
            token = _get_token()
            url = f"https://huggingface.co/{AGENT_REPO_ID}/resolve/main/{AGENT_MODEL_FILENAME}"
            
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            temp_path = model_path + ".downloading"
            
            with requests.get(url, headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192 * 1024): # 8MB chunks
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (100 * 1024 * 1024) < (8192 * 1024):
                                # Print progress ~ every 100MB
                                print(f"[Agent] Download progress: {downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({(downloaded/total_size)*100:.1f}%)")
            
            if os.path.exists(model_path):
                os.remove(model_path)
            shutil.move(temp_path, model_path)

            db = SessionLocal()
            try:
                existing = db.query(ModelRecord).filter(ModelRecord.file_path == model_path).first()
                if not existing:
                    new_model = ModelRecord(
                        name="NPU-STACK System Agent (Phi-3-mini)",
                        framework="llama.cpp",
                        architecture="phi3",
                        format="gguf",
                        file_size=os.path.getsize(model_path),
                        size_mb=os.path.getsize(model_path) / (1024 * 1024),
                        file_path=model_path,
                        quant_type="Q4",
                        description=f"System Agent model: {AGENT_REPO_ID}/{AGENT_MODEL_FILENAME}"
                    )
                    db.add(new_model)
                    db.commit()
            finally:
                db.close()

            print("[Agent] Download complete.")
        except Exception as e:
            print(f"[Agent] Download failed: {e}")


@router.post("/init")
def initialize_agent(background_tasks: BackgroundTasks):
    """Start background download of the agent model if it doesn't exist."""
    if os.path.exists(_model_path()):
        return {"message": "Agent model already downloaded.", "path": _model_path()}
    background_tasks.add_task(_download_model_task)
    return {"message": "Agent download started in background."}


# ── Start (Load into memory) ───────────────────────────


@router.post("/start")
def start_agent(background_tasks: BackgroundTasks):
    """Load the system agent GGUF model. Triggers auto-download if missing."""
    model_path = _model_path()
    
    if not os.path.exists(model_path):
        # Auto-trigger download
        print(f"[Agent] Model missing at {model_path}. Triggering auto-download.")
        background_tasks.add_task(_download_model_task)
        return {
            "success": False, 
            "status": "downloading",
            "message": "Agent model is missing. Download has been started automatically. Please try again in a few minutes."
        }

    from services.gguf_service import load_model

    try:
        result = load_model(model_path, n_ctx=4096, n_gpu_layers=-1)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(500, f"Failed to load agent model: {str(e)}")


# ── Chat ────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are the NPU-STACK System Assistant. You help users navigate the NPU-STACK AI Factory, "
    "explaining how to convert models to GGUF, RKNN, or ONNX, how to fine-tune using Unsloth, "
    "and how to deploy to edge hardware like Vitis DPU and NVIDIA NIM. Be concise, technical, and helpful."
)


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 512


@router.post("/chat")
def agent_chat(req: ChatRequest):
    """Chat with the system agent using the loaded GGUF model."""
    model_path = _model_path()

    from services.gguf_service import chat_completion, get_loaded_models

    loaded = get_loaded_models()
    if not any(m.get("filename") == AGENT_MODEL_FILENAME for m in loaded):
        raise HTTPException(400, "Agent model is not loaded. Call /start first.")

    # Prepend system prompt
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + req.messages

    result = chat_completion(
        model_path=model_path,
        messages=full_messages,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    return result


# ── Generate Dataset ────────────────────────────────────


@router.post("/generate-dataset")
def generate_knowledge_dataset():
    """Generates the npu_stack_knowledge.jsonl dataset from local docs."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    dataset_dir = os.path.dirname(_dataset_path())
    os.makedirs(dataset_dir, exist_ok=True)

    readme_path = os.path.join(root_dir, "README.md")
    knowledge_items = []

    # 1. Base Identity
    knowledge_items.append({
        "instruction": "Who are you and what is your purpose?",
        "input": "",
        "output": (
            "I am the NPU-STACK System Assistant. My purpose is to guide users through the NPU-STACK platform, "
            "helping them train, convert, quantize, and deploy AI models across local CPUs, GPUs, and Neural "
            "Processing Units (NPUs)."
        ),
    })

    # 2. Extract from README
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
            chunks = [content[i : i + 1000] for i in range(0, len(content), 1000)]
            for i, chunk in enumerate(chunks):
                knowledge_items.append({
                    "instruction": "Tell me about NPU-STACK features.",
                    "input": f"Part {i + 1}",
                    "output": chunk,
                })

    dataset_path = _dataset_path()
    with open(dataset_path, "w", encoding="utf-8") as f:
        for item in knowledge_items:
            f.write(json.dumps(item) + "\n")

    return {"message": f"Generated {len(knowledge_items)} items.", "path": dataset_path}
