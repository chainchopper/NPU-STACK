"""GGUF Pipeline — Convert, quantize, inspect, edit, and merge GGUF models.

Complements gguf_service.py (inference) with production-grade pipeline tools:
  - Read/edit GGUF metadata (architecture, vocab, quant info)
  - Quantize via llama.cpp CLI (Q2_K through Q8_0 + imatrix)
  - LoRA→GGUF merge (apply adapter weights to base model)
  - SafeTensors/HuggingFace → GGUF conversion
  - GGUF split/join for large models

Requires: llama.cpp binaries in PATH or configured location.
"""

import os
import json
import struct
import subprocess
import shutil
import time
from typing import Optional, List, Dict


# ── Constants ───────────────────────────────────────────

GGUF_MAGIC = 0x46554747  # "GGUF" in little-endian
GGUF_VERSION_3 = 3

# Quantization types available via llama-quantize
QUANT_TYPES = {
    "Q2_K":     {"bits": 2, "description": "Smallest, lowest quality"},
    "Q3_K_S":   {"bits": 3, "description": "Small, low quality"},
    "Q3_K_M":   {"bits": 3, "description": "Small, medium quality"},
    "Q3_K_L":   {"bits": 3, "description": "Small, better quality"},
    "Q4_0":     {"bits": 4, "description": "Legacy 4-bit, fast"},
    "Q4_1":     {"bits": 4, "description": "Legacy 4-bit, slightly better"},
    "Q4_K_S":   {"bits": 4, "description": "Small 4-bit, good quality"},
    "Q4_K_M":   {"bits": 4, "description": "Medium 4-bit, recommended"},
    "Q5_0":     {"bits": 5, "description": "Legacy 5-bit"},
    "Q5_1":     {"bits": 5, "description": "Legacy 5-bit, better"},
    "Q5_K_S":   {"bits": 5, "description": "Small 5-bit, high quality"},
    "Q5_K_M":   {"bits": 5, "description": "Medium 5-bit, very good"},
    "Q6_K":     {"bits": 6, "description": "6-bit, near-lossless"},
    "Q8_0":     {"bits": 8, "description": "8-bit, best quality"},
    "F16":      {"bits": 16, "description": "Float16, no quantization"},
    "F32":      {"bits": 32, "description": "Float32, original precision"},
    "IQ1_S":    {"bits": 1, "description": "1-bit imatrix, experimental"},
    "IQ2_XXS":  {"bits": 2, "description": "2-bit imatrix, very small"},
    "IQ2_XS":   {"bits": 2, "description": "2-bit imatrix, small"},
    "IQ3_XXS":  {"bits": 3, "description": "3-bit imatrix"},
    "IQ4_NL":   {"bits": 4, "description": "4-bit imatrix, non-linear"},
}

# Supported LLM architectures for conversion
SUPPORTED_ARCHITECTURES = [
    "llama", "mistral", "mixtral", "phi", "phi3", "gemma", "gemma2",
    "qwen", "qwen2", "deepseek", "deepseek2", "starcoder", "starcoder2",
    "codellama", "falcon", "mpt", "gpt2", "gpt-j", "gpt-neox",
    "bloom", "baichuan", "internlm", "internlm2", "yi",
    "command-r", "dbrx", "olmo", "stablelm", "refact",
    "persimmon", "jina-bert", "nomic-bert", "mamba", "rwkv",
    "arctic", "chatglm", "glm", "exaone", "t5",
]


# ── GGUF Metadata Reader ───────────────────────────────

def read_gguf_metadata(file_path: str) -> dict:
    """Read GGUF file header and metadata without loading the full model.

    Parses the binary GGUF header to extract:
    - Version, tensor count, metadata KV count
    - Architecture, quantization type, context length
    - Vocabulary info, tokenizer type
    - Author, description, license
    """
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        with open(file_path, "rb") as f:
            # Read magic number
            magic = struct.unpack("<I", f.read(4))[0]
            if magic != GGUF_MAGIC:
                return {"success": False, "error": f"Not a GGUF file (magic: 0x{magic:08X})"}

            # Read version
            version = struct.unpack("<I", f.read(4))[0]

            # Read tensor count and metadata KV count
            tensor_count = struct.unpack("<Q", f.read(8))[0]
            metadata_kv_count = struct.unpack("<Q", f.read(8))[0]

            # Parse metadata key-value pairs
            metadata = {}
            for _ in range(min(metadata_kv_count, 500)):  # Cap at 500 to avoid hangs
                try:
                    key = _read_gguf_string(f)
                    value_type = struct.unpack("<I", f.read(4))[0]
                    value = _read_gguf_value(f, value_type)
                    if key and value is not None:
                        metadata[key] = value
                except Exception:
                    break

        # Extract commonly needed fields
        arch = metadata.get("general.architecture", "unknown")
        result = {
            "success": True,
            "file_path": file_path,
            "file_size": os.path.getsize(file_path),
            "version": version,
            "tensor_count": tensor_count,
            "metadata_kv_count": metadata_kv_count,
            "architecture": arch,
            "model_name": metadata.get("general.name", ""),
            "description": metadata.get("general.description", ""),
            "author": metadata.get("general.author", ""),
            "license": metadata.get("general.license", ""),
            "quantization_version": metadata.get("general.quantization_version"),
            "file_type": metadata.get("general.file_type"),
            "context_length": metadata.get(f"{arch}.context_length"),
            "embedding_length": metadata.get(f"{arch}.embedding_length"),
            "block_count": metadata.get(f"{arch}.block_count"),
            "head_count": metadata.get(f"{arch}.attention.head_count"),
            "head_count_kv": metadata.get(f"{arch}.attention.head_count_kv"),
            "vocab_size": metadata.get(f"{arch}.vocab_size") or metadata.get("tokenizer.ggml.tokens", None),
            "tokenizer_model": metadata.get("tokenizer.ggml.model", ""),
        }

        # Include raw metadata for advanced users (filter large arrays)
        filtered = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                filtered[k] = v
            elif isinstance(v, list) and len(v) <= 10:
                filtered[k] = v
            elif isinstance(v, list):
                filtered[k] = f"[array of {len(v)} items]"
        result["raw_metadata"] = filtered

        return result

    except Exception as e:
        return {"success": False, "error": f"Failed to read GGUF: {str(e)}"}


def _read_gguf_string(f) -> str:
    """Read a GGUF string (uint64 length + bytes)."""
    length = struct.unpack("<Q", f.read(8))[0]
    if length > 1_000_000:
        return ""
    return f.read(length).decode("utf-8", errors="replace")


def _read_gguf_value(f, value_type: int):
    """Read a GGUF metadata value based on its type."""
    # GGUF value types
    if value_type == 0:    # UINT8
        return struct.unpack("<B", f.read(1))[0]
    elif value_type == 1:  # INT8
        return struct.unpack("<b", f.read(1))[0]
    elif value_type == 2:  # UINT16
        return struct.unpack("<H", f.read(2))[0]
    elif value_type == 3:  # INT16
        return struct.unpack("<h", f.read(2))[0]
    elif value_type == 4:  # UINT32
        return struct.unpack("<I", f.read(4))[0]
    elif value_type == 5:  # INT32
        return struct.unpack("<i", f.read(4))[0]
    elif value_type == 6:  # FLOAT32
        return struct.unpack("<f", f.read(4))[0]
    elif value_type == 7:  # BOOL
        return struct.unpack("<B", f.read(1))[0] != 0
    elif value_type == 8:  # STRING
        return _read_gguf_string(f)
    elif value_type == 9:  # ARRAY
        arr_type = struct.unpack("<I", f.read(4))[0]
        arr_len = struct.unpack("<Q", f.read(8))[0]
        if arr_len > 100_000:
            # Skip large arrays (vocab tokens, etc.)
            return f"[array: type={arr_type}, len={arr_len}]"
        values = []
        for _ in range(arr_len):
            v = _read_gguf_value(f, arr_type)
            values.append(v)
        return values
    elif value_type == 10:  # UINT64
        return struct.unpack("<Q", f.read(8))[0]
    elif value_type == 11:  # INT64
        return struct.unpack("<q", f.read(8))[0]
    elif value_type == 12:  # FLOAT64
        return struct.unpack("<d", f.read(8))[0]
    else:
        return None


# ── CLI Tool Detection ──────────────────────────────────

def _find_llama_cpp_tool(tool_name: str) -> Optional[str]:
    """Find a llama.cpp binary in PATH or common locations."""
    # Check PATH first
    path = shutil.which(tool_name)
    if path:
        return path

    # Check common install locations
    search_dirs = [
        os.path.expanduser("~/llama.cpp/build/bin"),
        os.path.expanduser("~/llama.cpp"),
        "/usr/local/bin",
        "/opt/llama.cpp/build/bin",
    ]

    # Windows paths
    if os.name == "nt":
        search_dirs.extend([
            os.path.expanduser("~/llama.cpp/build/bin/Release"),
            "C:/llama.cpp/build/bin/Release",
            "C:/llama.cpp",
        ])

    for d in search_dirs:
        candidate = os.path.join(d, tool_name)
        if os.path.isfile(candidate):
            return candidate
        # Try with .exe on Windows
        if os.name == "nt":
            candidate_exe = candidate + ".exe"
            if os.path.isfile(candidate_exe):
                return candidate_exe

    return None


def detect_llama_cpp_tools() -> dict:
    """Detect available llama.cpp CLI tools."""
    tools = {
        "llama-quantize": _find_llama_cpp_tool("llama-quantize"),
        "llama-gguf-split": _find_llama_cpp_tool("llama-gguf-split"),
        "llama-cli": _find_llama_cpp_tool("llama-cli"),
        "llama-server": _find_llama_cpp_tool("llama-server"),
        "llama-imatrix": _find_llama_cpp_tool("llama-imatrix"),
    }

    # Legacy tool names (older llama.cpp builds)
    if not tools["llama-quantize"]:
        tools["llama-quantize"] = _find_llama_cpp_tool("quantize")
    if not tools["llama-cli"]:
        tools["llama-cli"] = _find_llama_cpp_tool("main")

    # Also check for convert scripts
    convert_script = _find_llama_cpp_tool("convert_hf_to_gguf.py")
    if not convert_script:
        # Check in llama.cpp source directories
        for d in [os.path.expanduser("~/llama.cpp"), "C:/llama.cpp"]:
            candidate = os.path.join(d, "convert_hf_to_gguf.py")
            if os.path.isfile(candidate):
                convert_script = candidate
                break
    tools["convert_hf_to_gguf"] = convert_script

    return {
        "tools": {k: v for k, v in tools.items() if v},
        "available": {k: v is not None for k, v in tools.items()},
        "any_available": any(v is not None for v in tools.values()),
    }


# ── Quantization ────────────────────────────────────────

def quantize_gguf(
    input_path: str,
    output_dir: str,
    quant_type: str = "Q4_K_M",
    output_name: Optional[str] = None,
    n_threads: Optional[int] = None,
    imatrix_path: Optional[str] = None,
) -> dict:
    """Quantize a GGUF model to a lower precision.

    Args:
        input_path: Path to the source GGUF file (usually F16 or F32)
        output_dir: Directory for the quantized output
        quant_type: Quantization type (Q4_K_M, Q5_K_S, IQ4_NL, etc.)
        output_name: Custom output filename (auto-generated if None)
        n_threads: Number of threads (None = auto)
        imatrix_path: Path to importance matrix for IQ quantization

    Returns:
        Dict with success status, output path, and size info
    """
    quant_upper = quant_type.upper()
    if quant_upper not in QUANT_TYPES:
        return {
            "success": False,
            "error": f"Unknown quantization type: {quant_type}. Available: {list(QUANT_TYPES.keys())}",
        }

    if not os.path.isfile(input_path):
        return {"success": False, "error": f"Input file not found: {input_path}"}

    tools = detect_llama_cpp_tools()
    quantize_bin = tools["tools"].get("llama-quantize")
    if not quantize_bin:
        return {
            "success": False,
            "error": "llama-quantize not found. Install llama.cpp and add to PATH.",
            "install": "https://github.com/ggerganov/llama.cpp",
        }

    os.makedirs(output_dir, exist_ok=True)

    if not output_name:
        base = os.path.splitext(os.path.basename(input_path))[0]
        # Remove existing quant suffix if present
        for qt in QUANT_TYPES:
            base = base.replace(f"-{qt.lower()}", "").replace(f"_{qt.lower()}", "")
            base = base.replace(f"-{qt}", "").replace(f"_{qt}", "")
        output_name = f"{base}-{quant_upper}.gguf"

    output_path = os.path.join(output_dir, output_name)

    cmd = [quantize_bin]

    # Add imatrix if provided (required for IQ quant types)
    if imatrix_path and os.path.isfile(imatrix_path):
        cmd.extend(["--imatrix", imatrix_path])
    elif quant_upper.startswith("IQ") and not imatrix_path:
        return {
            "success": False,
            "error": f"{quant_upper} quantization requires an importance matrix. "
                     "Generate one first with generate_imatrix().",
        }

    cmd.extend([input_path, output_path, quant_upper])

    if n_threads:
        cmd.extend(["--threads", str(n_threads)])

    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=7200,  # 2 hour timeout for large models
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Quantization failed: {result.stderr[-500:]}",
                "cmd": " ".join(cmd),
            }

        input_size = os.path.getsize(input_path)
        output_size = os.path.getsize(output_path)

        return {
            "success": True,
            "input_path": input_path,
            "output_path": output_path,
            "quant_type": quant_upper,
            "input_size": input_size,
            "output_size": output_size,
            "compression_ratio": round(input_size / max(output_size, 1), 2),
            "elapsed_seconds": round(elapsed, 1),
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Quantization timed out (exceeded 2 hours)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Importance Matrix Generation ────────────────────────

def generate_imatrix(
    model_path: str,
    output_dir: str,
    calibration_file: Optional[str] = None,
    n_chunks: int = 100,
) -> dict:
    """Generate an importance matrix for high-quality IQ quantization.

    Args:
        model_path: Path to the source GGUF model
        output_dir: Directory for the imatrix output
        calibration_file: Text file for calibration (uses wiki.train.raw if None)
        n_chunks: Number of chunks to process

    Returns:
        Dict with path to generated imatrix file
    """
    tools = detect_llama_cpp_tools()
    imatrix_bin = tools["tools"].get("llama-imatrix")
    if not imatrix_bin:
        return {
            "success": False,
            "error": "llama-imatrix not found. Install llama.cpp and add to PATH.",
        }

    if not os.path.isfile(model_path):
        return {"success": False, "error": f"Model not found: {model_path}"}

    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(model_path))[0]
    output_path = os.path.join(output_dir, f"{base}.imatrix")

    cmd = [
        imatrix_bin,
        "-m", model_path,
        "-o", output_path,
        "--chunks", str(n_chunks),
    ]

    if calibration_file and os.path.isfile(calibration_file):
        cmd.extend(["-f", calibration_file])

    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=14400,  # 4 hour timeout
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            return {"success": False, "error": f"imatrix generation failed: {result.stderr[-500:]}"}

        return {
            "success": True,
            "output_path": output_path,
            "elapsed_seconds": round(elapsed, 1),
            "model": model_path,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "imatrix generation timed out (exceeded 4 hours)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── HuggingFace → GGUF Conversion ──────────────────────

def convert_hf_to_gguf(
    model_dir: str,
    output_dir: str,
    output_type: str = "f16",
    vocab_type: Optional[str] = None,
) -> dict:
    """Convert a HuggingFace/SafeTensors model to GGUF format.

    Uses llama.cpp's convert_hf_to_gguf.py script.

    Args:
        model_dir: Path to HuggingFace model directory (with config.json)
        output_dir: Directory for the GGUF output
        output_type: Output data type (f16, f32, q8_0)
        vocab_type: Vocabulary type override (spm, bpe, hfft)

    Returns:
        Dict with success status and output path
    """
    tools = detect_llama_cpp_tools()
    convert_script = tools["tools"].get("convert_hf_to_gguf")
    if not convert_script:
        return {
            "success": False,
            "error": "convert_hf_to_gguf.py not found. Clone llama.cpp repo.",
            "install": "git clone https://github.com/ggerganov/llama.cpp",
        }

    if not os.path.isdir(model_dir):
        return {"success": False, "error": f"Model directory not found: {model_dir}"}

    # Check for config.json
    config_path = os.path.join(model_dir, "config.json")
    if not os.path.isfile(config_path):
        return {"success": False, "error": f"No config.json in {model_dir}. Not a valid HuggingFace model."}

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "python", convert_script,
        model_dir,
        "--outfile", os.path.join(output_dir, "model.gguf"),
        "--outtype", output_type,
    ]

    if vocab_type:
        cmd.extend(["--vocab-type", vocab_type])

    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=3600,  # 1 hour timeout
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            return {"success": False, "error": f"Conversion failed: {result.stderr[-500:]}"}

        # Find the output file
        output_file = os.path.join(output_dir, "model.gguf")
        if not os.path.isfile(output_file):
            # Try to find any .gguf file in output dir
            for f in os.listdir(output_dir):
                if f.endswith(".gguf"):
                    output_file = os.path.join(output_dir, f)
                    break

        return {
            "success": True,
            "output_path": output_file,
            "output_type": output_type,
            "file_size": os.path.getsize(output_file) if os.path.isfile(output_file) else 0,
            "elapsed_seconds": round(elapsed, 1),
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Conversion timed out (exceeded 1 hour)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── LoRA Merge ──────────────────────────────────────────

def merge_lora_to_gguf(
    base_model_path: str,
    lora_path: str,
    output_dir: str,
    output_name: Optional[str] = None,
    scale: float = 1.0,
    n_threads: Optional[int] = None,
) -> dict:
    """Merge a LoRA adapter into a base GGUF model.

    Uses llama.cpp's built-in LoRA merging capability.

    Args:
        base_model_path: Path to the base GGUF model
        lora_path: Path to the LoRA adapter (GGUF format)
        output_dir: Directory for the merged output
        output_name: Custom output filename
        scale: LoRA scaling factor (default 1.0)
        n_threads: Number of threads

    Returns:
        Dict with success status and merged model path
    """
    if not os.path.isfile(base_model_path):
        return {"success": False, "error": f"Base model not found: {base_model_path}"}
    if not os.path.isfile(lora_path):
        return {"success": False, "error": f"LoRA adapter not found: {lora_path}"}

    # Use llama-cli with --lora flag for merging
    tools = detect_llama_cpp_tools()

    # Try export-lora tool first (newer llama.cpp)
    export_lora = _find_llama_cpp_tool("llama-export-lora")
    if export_lora:
        os.makedirs(output_dir, exist_ok=True)
        if not output_name:
            base = os.path.splitext(os.path.basename(base_model_path))[0]
            lora_name = os.path.splitext(os.path.basename(lora_path))[0]
            output_name = f"{base}-{lora_name}-merged.gguf"

        output_path = os.path.join(output_dir, output_name)

        cmd = [
            export_lora,
            "-m", base_model_path,
            "-o", output_path,
            "--lora", lora_path,
            "--lora-scale", str(scale),
        ]

        if n_threads:
            cmd.extend(["--threads", str(n_threads)])

        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=7200,
            )
            elapsed = time.time() - start_time

            if result.returncode != 0:
                return {"success": False, "error": f"LoRA merge failed: {result.stderr[-500:]}"}

            return {
                "success": True,
                "output_path": output_path,
                "base_model": base_model_path,
                "lora_adapter": lora_path,
                "lora_scale": scale,
                "file_size": os.path.getsize(output_path),
                "elapsed_seconds": round(elapsed, 1),
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "LoRA merge timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {
        "success": False,
        "error": "No LoRA merge tool found. Install llama.cpp with export-lora support.",
        "install": "https://github.com/ggerganov/llama.cpp",
    }


# ── GGUF Split/Join ────────────────────────────────────

def split_gguf(
    input_path: str,
    output_dir: str,
    max_size_gb: float = 4.0,
) -> dict:
    """Split a large GGUF model into smaller shards.

    Args:
        input_path: Path to the GGUF file
        output_dir: Directory for split shards
        max_size_gb: Maximum size per shard in GB

    Returns:
        Dict with output shard paths
    """
    tools = detect_llama_cpp_tools()
    split_bin = tools["tools"].get("llama-gguf-split")
    if not split_bin:
        return {"success": False, "error": "llama-gguf-split not found. Install llama.cpp."}

    if not os.path.isfile(input_path):
        return {"success": False, "error": f"File not found: {input_path}"}

    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]
    output_prefix = os.path.join(output_dir, base)

    max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)

    cmd = [
        split_bin,
        "--split",
        "--split-max-size", str(max_size_bytes),
        input_path,
        output_prefix,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            return {"success": False, "error": f"Split failed: {result.stderr[-500:]}"}

        # List generated shards
        shards = sorted([
            f for f in os.listdir(output_dir)
            if f.startswith(base) and f.endswith(".gguf")
        ])

        return {
            "success": True,
            "input_path": input_path,
            "shards": [os.path.join(output_dir, s) for s in shards],
            "shard_count": len(shards),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Pipeline Status ─────────────────────────────────────

def get_pipeline_status() -> dict:
    """Get full GGUF pipeline capabilities and tool availability."""
    tools = detect_llama_cpp_tools()

    # Check gguf Python library
    gguf_py_available = False
    gguf_py_version = None
    try:
        import gguf
        gguf_py_available = True
        gguf_py_version = getattr(gguf, "__version__", "installed")
    except ImportError:
        pass
    # Check llama-cpp-python (inference)
    inference_available = False
    try:
        from llama_cpp import Llama  # noqa: F401
        inference_available = True
    except ImportError:
        pass

    return {
        "llama_cpp_tools": tools,
        "gguf_python_lib": {
            "available": gguf_py_available,
            "version": gguf_py_version,
        },
        "quant_types_available": list(QUANT_TYPES.keys()),
        "supported_architectures": SUPPORTED_ARCHITECTURES,
        "capabilities": {
            "read_metadata": True,  # Always available (pure Python)
            "quantize": tools["available"].get("llama-quantize", False),
            "convert_hf": tools["available"].get("convert_hf_to_gguf", False),
            "imatrix": tools["available"].get("llama-imatrix", False),
            "split_join": tools["available"].get("llama-gguf-split", False),
            "lora_merge": _find_llama_cpp_tool("llama-export-lora") is not None,
            "inference": inference_available,
        },
    }

