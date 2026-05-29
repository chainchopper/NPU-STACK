"""
FastFlowLM (FLM) Service — CLI wrapper and OpenAI API proxy.

Manages the FLM runtime lifecycle:
  - Detect: is `flm` on PATH? what version?
  - List:   available models (flm list)
  - Pull:   download a model by tag (flm pull)
  - Serve:  start the FLM OpenAI server (flm serve)
  - Stop:   terminate the managed server
  - Proxy:  forward chat requests to FLM's OpenAI API
"""

import os
import re
import json
import shutil
import asyncio
import logging
import subprocess
from typing import Optional, Dict, Any, List, AsyncGenerator

import httpx

logger = logging.getLogger("flm_service")

# ────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────

FLM_DEFAULT_PORT = 52625
FLM_BASE_URL = f"http://127.0.0.1:{FLM_DEFAULT_PORT}"
FLM_API_URL = f"{FLM_BASE_URL}/v1"

# Managed server process (singleton)
_server_process: Optional[asyncio.subprocess.Process] = None
_server_model: Optional[str] = None


# ────────────────────────────────────────────
# Detection
# ────────────────────────────────────────────

def detect_flm() -> Dict[str, Any]:
    """Check if FastFlowLM (flm) is available on PATH."""
    flm_path = shutil.which("flm")
    if not flm_path:
        return {"installed": False, "path": None, "version": None}

    version = None
    try:
        result = subprocess.run(
            ["flm", "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (result.stdout + result.stderr).strip()
        # Try to extract version like "v0.9.36" or "0.9.36"
        match = re.search(r"v?(\d+\.\d+\.\d+)", output)
        if match:
            version = match.group(1)
        elif output:
            version = output[:60]
    except Exception as e:
        logger.warning(f"Could not get FLM version: {e}")

    return {"installed": True, "path": flm_path, "version": version}


# ────────────────────────────────────────────
# Model Management
# ────────────────────────────────────────────

def list_models() -> List[Dict[str, str]]:
    """Run `flm list` and parse output into a list of dicts."""
    try:
        result = subprocess.run(
            ["flm", "list"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = result.stdout.strip()
        if not output:
            return []

        models = []
        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.startswith("NAME") or line.startswith("-"):
                continue
            # FLM list format is typically: NAME  SIZE  MODIFIED
            parts = line.split()
            if parts:
                model = {"tag": parts[0]}
                if len(parts) >= 2:
                    model["size"] = parts[1]
                if len(parts) >= 3:
                    model["modified"] = " ".join(parts[2:])
                models.append(model)
        return models
    except FileNotFoundError:
        logger.error("FLM binary not found on PATH")
        return []
    except Exception as e:
        logger.error(f"Error listing FLM models: {e}")
        return []


async def pull_model(tag: str) -> AsyncGenerator[str, None]:
    """Run `flm pull <tag>` and stream progress lines."""
    try:
        process = await asyncio.create_subprocess_exec(
            "flm", "pull", tag,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        async for line in process.stdout:
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                yield json.dumps({"status": "downloading", "message": decoded}) + "\n"

        await process.wait()

        if process.returncode == 0:
            yield json.dumps({"status": "complete", "message": f"Model {tag} pulled successfully"}) + "\n"
        else:
            yield json.dumps({"status": "error", "message": f"Pull failed with exit code {process.returncode}"}) + "\n"

    except FileNotFoundError:
        yield json.dumps({"status": "error", "message": "FLM binary not found on PATH"}) + "\n"
    except Exception as e:
        yield json.dumps({"status": "error", "message": str(e)}) + "\n"


# ────────────────────────────────────────────
# Server Lifecycle
# ────────────────────────────────────────────

async def start_server(model_tag: str, port: int = FLM_DEFAULT_PORT) -> Dict[str, Any]:
    """Start `flm serve <model>` as a managed background process."""
    global _server_process, _server_model

    # Already running?
    if _server_process and _server_process.returncode is None:
        return {
            "status": "already_running",
            "model": _server_model,
            "port": port,
        }

    try:
        _server_process = await asyncio.create_subprocess_exec(
            "flm", "serve", model_tag, "--port", str(port),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _server_model = model_tag

        # Wait briefly for server to start
        await asyncio.sleep(3)

        # Check if it's actually up
        if _server_process.returncode is not None:
            # Process exited already — read output for error
            output = ""
            try:
                stdout, _ = await asyncio.wait_for(
                    _server_process.communicate(), timeout=5
                )
                output = stdout.decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            _server_process = None
            _server_model = None
            return {"status": "error", "message": f"Server exited immediately: {output}"}

        return {
            "status": "started",
            "model": model_tag,
            "port": port,
            "url": f"http://127.0.0.1:{port}/v1",
        }

    except FileNotFoundError:
        return {"status": "error", "message": "FLM binary not found on PATH"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def stop_server() -> Dict[str, Any]:
    """Terminate the managed FLM server process."""
    global _server_process, _server_model

    if _server_process is None or _server_process.returncode is not None:
        _server_process = None
        _server_model = None
        return {"status": "not_running"}

    try:
        _server_process.terminate()
        try:
            await asyncio.wait_for(_server_process.wait(), timeout=10)
        except asyncio.TimeoutError:
            _server_process.kill()
            await _server_process.wait()

        model = _server_model
        _server_process = None
        _server_model = None
        return {"status": "stopped", "model": model}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def get_server_status() -> Dict[str, Any]:
    """Check if the FLM server is responding."""
    info = detect_flm()

    # Check managed process
    managed_running = (
        _server_process is not None and _server_process.returncode is None
    )

    # Health-check the port regardless (user might have started flm serve manually)
    server_alive = False
    server_models = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{FLM_API_URL}/models")
            if resp.status_code == 200:
                server_alive = True
                data = resp.json()
                server_models = [m.get("id", m.get("model", "")) for m in data.get("data", [])]
    except Exception:
        pass

    return {
        **info,
        "server_running": server_alive,
        "server_managed": managed_running,
        "active_model": _server_model,
        "server_models": server_models,
        "port": FLM_DEFAULT_PORT,
        "api_url": FLM_API_URL,
    }


# ────────────────────────────────────────────
# Chat proxy
# ────────────────────────────────────────────

async def proxy_chat(
    messages: List[Dict[str, str]],
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    top_p: float = 1.0,
    stream: bool = False,
) -> Any:
    """Forward a chat completion request to the FLM OpenAI API."""

    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "stream": stream,
    }
    if model:
        payload["model"] = model

    if stream:
        return _proxy_chat_stream(payload)
    else:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{FLM_API_URL}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer flm"},
            )
            resp.raise_for_status()
            return resp.json()


async def _proxy_chat_stream(payload: dict) -> AsyncGenerator[str, None]:
    """Stream SSE chunks from FLM."""
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{FLM_API_URL}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer flm"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line + "\n\n"
                elif line == "data: [DONE]":
                    yield "data: [DONE]\n\n"


# ────────────────────────────────────────────
# Known model catalog (for frontend display)
# ────────────────────────────────────────────

FLM_MODEL_CATALOG = [
    {"tag": "llama3.2:1b", "family": "LLaMA", "params": "1B", "type": "llm", "ctx": "131072"},
    {"tag": "llama3.2:3b", "family": "LLaMA", "params": "3B", "type": "llm", "ctx": "131072"},
    {"tag": "llama3.1:8b", "family": "LLaMA", "params": "8B", "type": "llm", "ctx": "131072"},
    {"tag": "deepseek-r1:1.5b", "family": "DeepSeek", "params": "1.5B", "type": "llm", "ctx": "65536"},
    {"tag": "deepseek-r1:7b", "family": "DeepSeek", "params": "7B", "type": "llm", "ctx": "65536"},
    {"tag": "deepseek-r1:8b", "family": "DeepSeek", "params": "8B", "type": "llm", "ctx": "65536"},
    {"tag": "qwen2.5:1.5b", "family": "Qwen", "params": "1.5B", "type": "llm", "ctx": "131072"},
    {"tag": "qwen2.5:3b", "family": "Qwen", "params": "3B", "type": "llm", "ctx": "131072"},
    {"tag": "qwen2.5:7b", "family": "Qwen", "params": "7B", "type": "llm", "ctx": "131072"},
    {"tag": "qwen3:4b", "family": "Qwen", "params": "4B", "type": "llm", "ctx": "131072"},
    {"tag": "qwen3.5:4b", "family": "Qwen", "params": "4B", "type": "vlm", "ctx": "131072"},
    {"tag": "gemma3:1b", "family": "Gemma", "params": "1B", "type": "llm", "ctx": "32768"},
    {"tag": "gemma3:4b", "family": "Gemma", "params": "4B", "type": "llm", "ctx": "131072"},
    {"tag": "phi-4-mini", "family": "Phi", "params": "3.8B", "type": "llm", "ctx": "131072"},
    {"tag": "phi-4:14b", "family": "Phi", "params": "14B", "type": "llm", "ctx": "16384"},
    {"tag": "whisper:base", "family": "Whisper", "params": "74M", "type": "whisper", "ctx": "n/a"},
    {"tag": "whisper:small", "family": "Whisper", "params": "244M", "type": "whisper", "ctx": "n/a"},
    {"tag": "whisper:medium", "family": "Whisper", "params": "769M", "type": "whisper", "ctx": "n/a"},
    {"tag": "embeddinggemma:2b", "family": "EmbeddingGemma", "params": "2B", "type": "embed", "ctx": "8192"},
    {"tag": "gpt-oss:1b", "family": "gpt-oss", "params": "1B", "type": "llm", "ctx": "32768"},
    {"tag": "lfm2:3b", "family": "LiquidAI", "params": "3B", "type": "llm", "ctx": "131072"},
]
