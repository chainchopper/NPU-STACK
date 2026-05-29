"""
OpenAI-compatible Model Serving API — /v1 endpoints.

Drop-in replacement for OpenAI API. Works with:
  - openai Python/JS SDK
  - LangChain, LlamaIndex
  - Open WebUI, Chatbot UI
  - curl, fetch, Postman
  - Any app expecting OpenAI-format endpoints

Endpoints:
  GET  /v1/models              — List available models
  POST /v1/chat/completions    — Chat completion (streaming + non-streaming)
  POST /v1/completions         — Text completion (legacy)
  POST /v1/embeddings          — Generate text embeddings
  POST /v1/models/load         — Load a model into memory
  POST /v1/models/unload       — Unload a model from memory
"""

import os
import time
import json
import uuid
import asyncio
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(tags=["serving"])

# ────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────

API_KEY = os.environ.get("NPU_STACK_API_KEY", "")  # Empty = no auth required


def _check_api_key(request: Request):
    """Optional API key auth — only enforced if NPU_STACK_API_KEY is set."""
    if not API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header. Use: Bearer <api-key>")
    token = auth[len("Bearer "):]
    if token != API_KEY:
        raise HTTPException(403, "Invalid API key")


# ────────────────────────────────────────────
# Model State Manager
# ────────────────────────────────────────────

class _ModelManager:
    """Manages loaded models in memory for inference serving."""

    def __init__(self):
        self._loaded: Dict[str, dict] = {}  # model_name -> { "record", "pipeline", "type", "loaded_at" }

    @property
    def loaded_models(self):
        return self._loaded

    def is_loaded(self, name: str) -> bool:
        return name in self._loaded

    def get(self, name: str):
        return self._loaded.get(name)

    def load_model(self, record: ModelRecord) -> dict:
        """Load a model into memory for serving."""
        name = record.name
        if name in self._loaded:
            return self._loaded[name]

        file_path = record.file_path
        fmt = record.format
        framework = record.framework

        entry = {
            "record": {
                "id": record.id,
                "name": record.name,
                "framework": record.framework,
                "format": record.format,
                "file_path": record.file_path,
                "file_size": record.file_size,
                "description": record.description,
            },
            "pipeline": None,
            "session": None,
            "tokenizer": None,
            "type": "unknown",
            "loaded_at": time.time(),
        }

        # ─── Try loading as GGUF (llama-cpp-python) ───
        if fmt == "gguf" or file_path.endswith(".gguf"):
            try:
                from services.gguf_service import load_model as gguf_load, is_available as gguf_available
                if not gguf_available():
                    raise RuntimeError("llama-cpp-python not installed")
                gguf_info = gguf_load(
                    model_path=file_path,
                    n_ctx=4096,
                    n_gpu_layers=0,  # CPU by default; user can configure
                )
                entry["type"] = "gguf"
                entry["gguf_path"] = file_path
                self._loaded[name] = entry
                return entry
            except Exception as e:
                raise HTTPException(500, f"Failed to load GGUF model: {e}")

        # ─── Try loading as text generation (transformers) ───
        if fmt in ("pt", "pth", "bin", "safetensors") or framework == "pytorch":
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer
                model_dir = os.path.dirname(file_path)
                # Check if tokenizer config exists alongside model
                has_tokenizer = any(
                    os.path.exists(os.path.join(model_dir, f))
                    for f in ["tokenizer.json", "tokenizer_config.json", "vocab.json", "spiece.model"]
                )
                if has_tokenizer:
                    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
                    model = AutoModelForCausalLM.from_pretrained(model_dir, trust_remote_code=True)
                    entry["pipeline"] = model
                    entry["tokenizer"] = tokenizer
                    entry["type"] = "causal_lm"
                    self._loaded[name] = entry
                    return entry
            except Exception:
                pass

            # Try as a generic transformers pipeline
            try:
                from transformers import pipeline
                model_dir = os.path.dirname(file_path)
                pipe = pipeline("text-generation", model=model_dir, trust_remote_code=True)
                entry["pipeline"] = pipe
                entry["type"] = "text_generation_pipeline"
                self._loaded[name] = entry
                return entry
            except Exception:
                pass

        # ─── Try loading as ONNX model ───
        if fmt == "onnx":
            try:
                import onnxruntime as ort
                session = ort.InferenceSession(
                    file_path,
                    providers=ort.get_available_providers()
                )
                entry["session"] = session
                entry["type"] = "onnx"

                # Try loading a tokenizer if one sits alongside
                model_dir = os.path.dirname(file_path)
                try:
                    from transformers import AutoTokenizer
                    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
                    entry["tokenizer"] = tokenizer
                    entry["type"] = "onnx_lm"
                except Exception:
                    pass

                self._loaded[name] = entry
                return entry
            except Exception as e:
                raise HTTPException(500, f"Failed to load ONNX model: {e}")

        # ─── Try loading as OpenVINO model ───
        if fmt in ("openvino_ir", "xml"):
            try:
                import openvino as ov
                core = ov.Core()
                compiled = core.compile_model(file_path, "AUTO")
                entry["session"] = compiled
                entry["type"] = "openvino"
                self._loaded[name] = entry
                return entry
            except Exception as e:
                raise HTTPException(500, f"Failed to load OpenVINO model: {e}")

        # Generic fallback — register but can't serve
        entry["type"] = "unsupported"
        self._loaded[name] = entry
        return entry

    def unload_model(self, name: str):
        """Unload a model from memory."""
        if name in self._loaded:
            entry = self._loaded.pop(name)
            # Help garbage collector
            entry["pipeline"] = None
            entry["session"] = None
            entry["tokenizer"] = None
            return True
        return False

    def list_models_info(self) -> List[dict]:
        """Return OpenAI-format model list."""
        result = []
        for name, entry in self._loaded.items():
            result.append({
                "id": name,
                "object": "model",
                "created": int(entry["loaded_at"]),
                "owned_by": "npu-stack",
                "permission": [],
                "root": name,
                "parent": None,
            })
        return result


model_manager = _ModelManager()


# ────────────────────────────────────────────
# Pydantic Schemas (OpenAI-compatible)
# ────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 1.0
    stream: bool = False
    stop: Optional[List[str]] = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    n: int = 1


class CompletionRequest(BaseModel):
    model: str
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 1.0
    stream: bool = False
    stop: Optional[List[str]] = None
    n: int = 1


class EmbeddingRequest(BaseModel):
    model: str
    input: Any  # str or List[str]


class LoadModelRequest(BaseModel):
    name: str = Field(..., description="Model name (as registered in model registry)")


# ────────────────────────────────────────────
# Helper: Generate text from a loaded model
# ────────────────────────────────────────────

def _generate_text(model_entry: dict, prompt: str, max_tokens: int = 256,
                   temperature: float = 0.7, top_p: float = 1.0,
                   stop: Optional[List[str]] = None,
                   messages: Optional[List[dict]] = None) -> str:
    """Generate text from a loaded model (supports GGUF, transformers, ONNX+tokenizer)."""
    model_type = model_entry["type"]

    if model_type == "gguf":
        from services.gguf_service import chat_completion as gguf_chat, text_completion as gguf_text
        gguf_path = model_entry["gguf_path"]
        if messages:
            response = gguf_chat(
                model_path=gguf_path,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stop=stop,
            )
            return response["choices"][0]["message"]["content"]
        else:
            response = gguf_text(
                model_path=gguf_path,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stop=stop,
            )
            return response["choices"][0]["text"]

    elif model_type == "causal_lm":
        import torch
        model = model_entry["pipeline"]
        tokenizer = model_entry["tokenizer"]
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=max(temperature, 0.01),
                top_p=top_p,
                do_sample=temperature > 0,
            )
        decoded = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        if stop:
            for s in stop:
                if s in decoded:
                    decoded = decoded[:decoded.index(s)]
        return decoded

    elif model_type == "text_generation_pipeline":
        pipe = model_entry["pipeline"]
        result = pipe(
            prompt,
            max_new_tokens=max_tokens,
            temperature=max(temperature, 0.01),
            top_p=top_p,
            do_sample=temperature > 0,
        )
        text = result[0]["generated_text"]
        # Pipeline returns full text including prompt
        if text.startswith(prompt):
            text = text[len(prompt):]
        if stop:
            for s in stop:
                if s in text:
                    text = text[:text.index(s)]
        return text

    elif model_type == "onnx_lm":
        import numpy as np
        session = model_entry["session"]
        tokenizer = model_entry["tokenizer"]
        inputs = tokenizer(prompt, return_tensors="np")

        # Discover which inputs the ONNX model expects
        model_input_names = [i.name for i in session.get_inputs()]
        model_input_shapes = {i.name: i.shape for i in session.get_inputs()}

        # Build initial feed from tokenizer outputs (input_ids, attention_mask)
        input_feed = {k: v for k, v in inputs.items() if k in model_input_names}

        # Add position_ids if required
        if "position_ids" in model_input_names and "position_ids" not in input_feed:
            seq_len = input_feed["input_ids"].shape[1]
            input_feed["position_ids"] = np.arange(seq_len, dtype=np.int64).reshape(1, -1)

        # Add zero-initialized past_key_values if required (KV-cache models)
        kv_inputs = [n for n in model_input_names if n.startswith("past_key_values")]
        if kv_inputs:
            batch_size = input_feed["input_ids"].shape[0]
            for kv_name in kv_inputs:
                shape = model_input_shapes[kv_name]
                # shape is typically [batch, num_heads, past_seq_len, head_dim]
                # Replace dynamic dims with concrete values
                concrete_shape = []
                for dim in shape:
                    if isinstance(dim, int) and dim > 0:
                        concrete_shape.append(dim)
                    elif isinstance(dim, str) and "batch" in dim.lower():
                        concrete_shape.append(batch_size)
                    elif isinstance(dim, str) and ("past" in dim.lower() or "seq" in dim.lower()):
                        concrete_shape.append(0)  # empty past for first inference
                    else:
                        concrete_shape.append(0 if dim == 0 or (isinstance(dim, str) and "past" in dim.lower()) else 1)
                input_feed[kv_name] = np.zeros(concrete_shape, dtype=np.float32)

        # Autoregressive generation loop
        generated_tokens = []
        eos_id = getattr(tokenizer, "eos_token_id", None)

        for step in range(min(max_tokens, 512)):
            try:
                outputs = session.run(None, input_feed)
            except Exception as e:
                if not generated_tokens:
                    raise HTTPException(500, f"ONNX inference failed: {e}")
                break

            logits = outputs[0]
            next_token_logits = logits[:, -1, :]

            # Apply temperature
            if temperature > 0 and temperature != 1.0:
                next_token_logits = next_token_logits / max(temperature, 0.01)

            next_token_id = int(np.argmax(next_token_logits, axis=-1)[0])

            if eos_id is not None and next_token_id == eos_id:
                break

            generated_tokens.append(next_token_id)

            # Check stop sequences
            partial = tokenizer.decode(generated_tokens, skip_special_tokens=True)
            if stop:
                should_stop = False
                for s in stop:
                    if s in partial:
                        partial = partial[:partial.index(s)]
                        should_stop = True
                        break
                if should_stop:
                    return partial

            # Update inputs for next step
            next_id_arr = np.array([[next_token_id]], dtype=np.int64)
            input_feed["input_ids"] = next_id_arr
            if "attention_mask" in input_feed:
                input_feed["attention_mask"] = np.concatenate(
                    [input_feed["attention_mask"], np.ones((1, 1), dtype=np.int64)], axis=1
                )
            if "position_ids" in input_feed:
                last_pos = input_feed["position_ids"][0, -1] if input_feed["position_ids"].shape[1] > 0 else -1
                input_feed["position_ids"] = np.array([[int(last_pos) + 1]], dtype=np.int64)

            # Update KV cache from model outputs (outputs[1:] are typically the new KV states)
            if kv_inputs and len(outputs) > 1:
                kv_outputs = outputs[1:]
                for i, kv_name in enumerate(sorted(kv_inputs)):
                    if i < len(kv_outputs):
                        input_feed[kv_name] = kv_outputs[i]

        decoded = tokenizer.decode(generated_tokens, skip_special_tokens=True)
        return decoded

    else:
        raise HTTPException(400, f"Model type '{model_type}' does not support text generation. "
                                 f"Load a causal LM, GGUF, or text-generation model.")


async def _generate_text_streaming(model_entry: dict, prompt: str, max_tokens: int = 256,
                                    temperature: float = 0.7, top_p: float = 1.0,
                                    stop: Optional[List[str]] = None,
                                    messages: Optional[List[dict]] = None):
    """Streaming text generation — yields SSE chunks."""
    model_type = model_entry["type"]

    if model_type == "gguf":
        from services.gguf_service import chat_completion as gguf_chat, text_completion as gguf_text
        gguf_path = model_entry["gguf_path"]
        if messages:
            gen = gguf_chat(
                model_path=gguf_path, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
                top_p=top_p, stop=stop, stream=True,
            )
        else:
            gen = gguf_text(
                model_path=gguf_path, prompt=prompt,
                temperature=temperature, max_tokens=max_tokens,
                top_p=top_p, stop=stop, stream=True,
            )
        for chunk in gen:
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if not delta:
                text = chunk.get("choices", [{}])[0].get("text", "")
                delta = text
            if delta:
                yield delta

    elif model_type == "causal_lm":
        import torch
        from transformers import TextIteratorStreamer
        from threading import Thread

        model = model_entry["pipeline"]
        tokenizer = model_entry["tokenizer"]
        inputs = tokenizer(prompt, return_tensors="pt")

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs = {
            **inputs,
            "max_new_tokens": max_tokens,
            "temperature": max(temperature, 0.01),
            "top_p": top_p,
            "do_sample": temperature > 0,
            "streamer": streamer,
        }

        thread = Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()

        accumulated = ""
        for text_chunk in streamer:
            accumulated += text_chunk
            if stop and any(s in accumulated for s in stop):
                break
            yield text_chunk

        thread.join()

    elif model_type == "text_generation_pipeline":
        # Pipelines don't support streaming easily — fall back to full gen
        result = _generate_text(model_entry, prompt, max_tokens, temperature, top_p, stop)
        # Simulate streaming by yielding word by word
        words = result.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.02)

    else:
        result = _generate_text(model_entry, prompt, max_tokens, temperature, top_p, stop)
        yield result


# ────────────────────────────────────────────
# Routes: /v1/models
# ────────────────────────────────────────────

@router.get("/v1/models")
async def list_models(request: Request, db: Session = Depends(get_db)):
    """List all available models (OpenAI-compatible format).
    
    Shows loaded models first, then all registered models.
    """
    _check_api_key(request)

    # Include loaded models
    models = model_manager.list_models_info()

    # Also include all registered but not-loaded models
    all_records = db.query(ModelRecord).all()
    loaded_names = {m["id"] for m in models}

    for record in all_records:
        if record.name not in loaded_names:
            models.append({
                "id": record.name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "npu-stack",
                "permission": [],
                "root": record.name,
                "parent": None,
            })

    return {"object": "list", "data": models}


# ────────────────────────────────────────────
# Routes: /v1/chat/completions
# ────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request,
                           db: Session = Depends(get_db)):
    """OpenAI-compatible chat completion endpoint.
    
    Supports streaming (SSE) and non-streaming responses.
    
    Usage with openai Python SDK:
        client = openai.OpenAI(base_url="http://localhost:8000/v1", api_key="any")
        response = client.chat.completions.create(
            model="my-model",
            messages=[{"role": "user", "content": "Hello!"}]
        )
    """
    _check_api_key(request)

    # Auto-load model if not loaded
    entry = model_manager.get(body.model)
    if not entry:
        record = db.query(ModelRecord).filter(ModelRecord.name == body.model).first()
        if not record:
            raise HTTPException(404, f"Model '{body.model}' not found. Use GET /v1/models to see available models.")
        entry = model_manager.load_model(record)

    if entry["type"] == "unsupported":
        raise HTTPException(400, f"Model '{body.model}' format is not supported for text generation.")

    # For GGUF models, pass messages directly to llama-cpp-python
    messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]

    # Build prompt from messages (for non-GGUF models)
    prompt_parts = []
    for msg in body.messages:
        if msg.role == "system":
            prompt_parts.append(f"System: {msg.content}")
        elif msg.role == "user":
            prompt_parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            prompt_parts.append(f"Assistant: {msg.content}")
    prompt_parts.append("Assistant:")
    prompt = "\n".join(prompt_parts)

    # Use chat template if tokenizer supports it
    if entry.get("tokenizer") and hasattr(entry["tokenizer"], "apply_chat_template"):
        try:
            messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
            prompt = entry["tokenizer"].apply_chat_template(
                messages_dicts, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            pass  # Fall back to manual prompt

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if body.stream:
        async def sse_generator():
            prompt_tokens = len(prompt.split())
            completion_tokens = 0

            async for chunk in _generate_text_streaming(
                entry, prompt, body.max_tokens, body.temperature, body.top_p, body.stop,
                messages=messages_dicts,
            ):
                completion_tokens += len(chunk.split())
                data = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": body.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": chunk},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(data)}\n\n"

            # Final chunk
            final = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": body.model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    else:
        # Non-streaming
        generated = _generate_text(
            entry, prompt, body.max_tokens, body.temperature, body.top_p, body.stop,
            messages=messages_dicts,
        )

        prompt_tokens = len(prompt.split())
        completion_tokens = len(generated.split())

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": body.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": generated},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


# ────────────────────────────────────────────
# Routes: /v1/completions
# ────────────────────────────────────────────

@router.post("/v1/completions")
async def text_completions(body: CompletionRequest, request: Request,
                           db: Session = Depends(get_db)):
    """Legacy text completion endpoint (OpenAI-compatible)."""
    _check_api_key(request)

    entry = model_manager.get(body.model)
    if not entry:
        record = db.query(ModelRecord).filter(ModelRecord.name == body.model).first()
        if not record:
            raise HTTPException(404, f"Model '{body.model}' not found.")
        entry = model_manager.load_model(record)

    if entry["type"] == "unsupported":
        raise HTTPException(400, f"Model '{body.model}' does not support text completion.")

    completion_id = f"cmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if body.stream:
        async def sse_generator():
            async for chunk in _generate_text_streaming(
                entry, body.prompt, body.max_tokens, body.temperature, body.top_p, body.stop
            ):
                data = {
                    "id": completion_id,
                    "object": "text_completion",
                    "created": created,
                    "model": body.model,
                    "choices": [{
                        "text": chunk,
                        "index": 0,
                        "logprobs": None,
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(data)}\n\n"

            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    else:
        generated = _generate_text(
            entry, body.prompt, body.max_tokens, body.temperature, body.top_p, body.stop
        )

        prompt_tokens = len(body.prompt.split())
        completion_tokens = len(generated.split())

        return {
            "id": completion_id,
            "object": "text_completion",
            "created": created,
            "model": body.model,
            "choices": [{
                "text": generated,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


# ────────────────────────────────────────────
# Routes: /v1/embeddings
# ────────────────────────────────────────────

@router.post("/v1/embeddings")
async def create_embeddings(body: EmbeddingRequest, request: Request,
                            db: Session = Depends(get_db)):
    """Generate text embeddings (OpenAI-compatible format)."""
    _check_api_key(request)

    entry = model_manager.get(body.model)
    if not entry:
        record = db.query(ModelRecord).filter(ModelRecord.name == body.model).first()
        if not record:
            raise HTTPException(404, f"Model '{body.model}' not found.")
        entry = model_manager.load_model(record)

    # Normalize input to list
    texts = body.input if isinstance(body.input, list) else [body.input]

    embeddings = []

    # Use sentence-transformers if available
    try:
        from sentence_transformers import SentenceTransformer
        # If model is already a SentenceTransformer
        if not hasattr(entry, "_st_model"):
            model_dir = os.path.dirname(entry["record"]["file_path"])
            st_model = SentenceTransformer(model_dir)
            entry["_st_model"] = st_model
        else:
            st_model = entry["_st_model"]

        vecs = st_model.encode(texts)
        for i, vec in enumerate(vecs):
            embeddings.append({
                "object": "embedding",
                "index": i,
                "embedding": vec.tolist(),
            })
    except Exception:
        # Fallback: use transformers model hidden states
        if entry.get("tokenizer") and entry.get("pipeline"):
            import torch
            import numpy as np
            model = entry["pipeline"]
            tokenizer = entry["tokenizer"]

            for i, text in enumerate(texts):
                inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
                with torch.no_grad():
                    outputs = model(**inputs, output_hidden_states=True)
                # Use mean of last hidden state as embedding
                hidden = outputs.hidden_states[-1]
                embedding = hidden.mean(dim=1).squeeze().cpu().numpy().tolist()
                embeddings.append({
                    "object": "embedding",
                    "index": i,
                    "embedding": embedding,
                })
        else:
            raise HTTPException(400, f"Model '{body.model}' does not support embeddings. "
                                     "Load a sentence-transformers or transformer model.")

    total_tokens = sum(len(t.split()) for t in texts)

    return {
        "object": "list",
        "data": embeddings,
        "model": body.model,
        "usage": {
            "prompt_tokens": total_tokens,
            "total_tokens": total_tokens,
        },
    }


# ────────────────────────────────────────────
# Routes: Model management
# ────────────────────────────────────────────

@router.post("/v1/models/load")
async def load_model(body: LoadModelRequest, request: Request,
                     db: Session = Depends(get_db)):
    """Load a model into memory for serving."""
    _check_api_key(request)

    if model_manager.is_loaded(body.name):
        return {"status": "already_loaded", "model": body.name}

    record = db.query(ModelRecord).filter(ModelRecord.name == body.name).first()
    if not record:
        raise HTTPException(404, f"Model '{body.name}' not found in registry.")

    entry = model_manager.load_model(record)

    return {
        "status": "loaded",
        "model": body.name,
        "type": entry["type"],
        "loaded_at": entry["loaded_at"],
    }


@router.post("/v1/models/unload")
async def unload_model(body: LoadModelRequest, request: Request):
    """Unload a model from memory."""
    _check_api_key(request)

    if model_manager.unload_model(body.name):
        return {"status": "unloaded", "model": body.name}
    raise HTTPException(404, f"Model '{body.name}' is not currently loaded.")


@router.get("/v1/models/status")
async def models_status(request: Request):
    """Get status of all loaded models."""
    _check_api_key(request)

    loaded = []
    for name, entry in model_manager.loaded_models.items():
        loaded.append({
            "name": name,
            "type": entry["type"],
            "loaded_at": entry["loaded_at"],
            "uptime_seconds": round(time.time() - entry["loaded_at"], 1),
            "has_tokenizer": entry["tokenizer"] is not None,
        })

    return {
        "loaded_count": len(loaded),
        "models": loaded,
    }
