"""GGUF model inference service using llama-cpp-python.

Provides native GGUF model loading and inference without conversion.
Supports chat completion, text completion, and embeddings.
"""

import os
import time
import uuid
from typing import Optional, List, Dict, Any

# Try importing llama-cpp-python
try:
    from llama_cpp import Llama
    HAS_LLAMA_CPP = True
except ImportError:
    Llama = None
    HAS_LLAMA_CPP = False


# Global model cache: {model_path: Llama instance}
_loaded_models: Dict[str, Any] = {}


def is_available() -> bool:
    """Check if llama-cpp-python is installed."""
    return HAS_LLAMA_CPP


def detect_gguf_info(file_path: str) -> dict:
    """Detect quantization level and metadata from a GGUF filename."""
    basename = os.path.basename(file_path).lower()
    
    # Common quantization patterns in GGUF filenames
    quant_patterns = [
        "q2_k", "q3_k_s", "q3_k_m", "q3_k_l",
        "q4_0", "q4_1", "q4_k_s", "q4_k_m",
        "q5_0", "q5_1", "q5_k_s", "q5_k_m",
        "q6_k", "q8_0", "f16", "f32",
        "iq1_s", "iq2_xxs", "iq2_xs", "iq3_xxs", "iq4_nl",
    ]
    
    detected_quant = "unknown"
    for pat in quant_patterns:
        if pat in basename:
            detected_quant = pat.upper()
            break
    
    return {
        "format": "gguf",
        "quantization": detected_quant,
        "filename": os.path.basename(file_path),
        "size_bytes": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
    }


def load_model(
    model_path: str,
    n_ctx: int = 4096,
    n_gpu_layers: int = 0,
    n_threads: Optional[int] = None,
    verbose: bool = False,
) -> dict:
    """Load a GGUF model into memory.
    
    Args:
        model_path: Path to the .gguf file
        n_ctx: Context window size (default 4096)
        n_gpu_layers: Number of layers to offload to GPU (0 = CPU only, -1 = all)
        n_threads: Number of CPU threads (None = auto)
        verbose: Whether to print llama.cpp logs
    
    Returns:
        Dict with model info
    """
    if not HAS_LLAMA_CPP:
        raise RuntimeError(
            "llama-cpp-python is not installed. "
            "Install with: pip install llama-cpp-python"
        )
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"GGUF file not found: {model_path}")
    
    if model_path in _loaded_models:
        return {"status": "already_loaded", "path": model_path}
    
    model = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        n_threads=n_threads or os.cpu_count(),
        verbose=verbose,
        embedding=True,  # Enable embedding support
    )
    
    _loaded_models[model_path] = model
    
    info = detect_gguf_info(model_path)
    info["status"] = "loaded"
    info["n_ctx"] = n_ctx
    info["n_gpu_layers"] = n_gpu_layers
    return info


def unload_model(model_path: str) -> dict:
    """Unload a GGUF model from memory."""
    if model_path in _loaded_models:
        del _loaded_models[model_path]
        return {"status": "unloaded", "path": model_path}
    return {"status": "not_loaded", "path": model_path}


def get_loaded_models() -> List[dict]:
    """Get list of currently loaded GGUF models."""
    result = []
    for path in _loaded_models:
        info = detect_gguf_info(path)
        info["status"] = "loaded"
        result.append(info)
    return result


def chat_completion(
    model_path: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 256,
    top_p: float = 1.0,
    stream: bool = False,
    stop: Optional[List[str]] = None,
) -> dict:
    """Generate a chat completion using a loaded GGUF model.
    
    Args:
        model_path: Path to the loaded GGUF model
        messages: List of message dicts with 'role' and 'content'
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        top_p: Nucleus sampling threshold
        stream: Whether to stream the response
        stop: Stop sequences
    
    Returns:
        OpenAI-compatible response dict
    """
    if model_path not in _loaded_models:
        raise RuntimeError(f"Model not loaded: {model_path}. Load it first.")
    
    model = _loaded_models[model_path]
    
    response = model.create_chat_completion(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=stream,
        stop=stop,
    )
    
    if stream:
        return response  # Returns a generator
    
    return response


def text_completion(
    model_path: str,
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 256,
    top_p: float = 1.0,
    stream: bool = False,
    stop: Optional[List[str]] = None,
) -> dict:
    """Generate a text completion using a loaded GGUF model."""
    if model_path not in _loaded_models:
        raise RuntimeError(f"Model not loaded: {model_path}. Load it first.")
    
    model = _loaded_models[model_path]
    
    response = model.create_completion(
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=stream,
        stop=stop,
    )
    
    if stream:
        return response
    
    return response


def create_embedding(
    model_path: str,
    input_text: str,
) -> dict:
    """Generate embeddings using a loaded GGUF model."""
    if model_path not in _loaded_models:
        raise RuntimeError(f"Model not loaded: {model_path}. Load it first.")
    
    model = _loaded_models[model_path]
    
    embedding = model.create_embedding(input_text)
    return embedding
