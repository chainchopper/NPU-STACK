"""Dataset Builder — Convert extracted data into training-ready datasets.

Supports multiple output formats: instruction tuning, chat, classification,
image captioning. Outputs JSONL, CSV, or Parquet.
"""

import os
import json
import hashlib
import re
from typing import Optional


# ── Output Formats ──────────────────────────────────────
DATASET_FORMATS = {
    "instruction": {
        "description": "Instruction tuning format (Alpaca-style)",
        "fields": ["instruction", "input", "output"],
    },
    "chat": {
        "description": "Chat/conversation format (ShareGPT/OpenAI)",
        "fields": ["messages"],
    },
    "classification": {
        "description": "Text classification format",
        "fields": ["text", "label"],
    },
    "raw_text": {
        "description": "Raw text corpus (one document per line)",
        "fields": ["text", "source"],
    },
    "qa": {
        "description": "Question-Answer pairs",
        "fields": ["question", "answer", "context"],
    },
    "image_caption": {
        "description": "Image captioning pairs",
        "fields": ["image_path", "caption"],
    },
}


def get_available_formats() -> list:
    """Return available dataset output formats."""
    return [{"id": k, **v} for k, v in DATASET_FORMATS.items()]


def build_dataset(
    extractions: list,
    output_format: str = "raw_text",
    output_dir: str = ".",
    dataset_name: str = "dataset",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    deduplicate: bool = True,
    min_length: int = 10,
    output_type: str = "jsonl",
) -> dict:
    """Build a training dataset from extraction results.

    Args:
        extractions: List of extraction results from data_extractor.
        output_format: Target dataset format (instruction, chat, raw_text, etc.)
        output_dir: Where to save the output file(s).
        dataset_name: Base name for the output file.
        chunk_size: Max characters per chunk for text splitting.
        chunk_overlap: Overlap between chunks.
        deduplicate: Remove duplicate entries.
        min_length: Minimum text length to include.
        output_type: File format: jsonl, csv, or parquet.

    Returns:
        dict with output path, record count, stats.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Collect all text content
    raw_texts = []
    for ext_result in extractions:
        if not ext_result.get("success"):
            continue
        text = ext_result.get("text", "").strip()
        if len(text) >= min_length:
            raw_texts.append({
                "text": text,
                "source": ext_result.get("metadata", {}).get("file_name", "unknown"),
                "file_type": ext_result.get("file_type", "unknown"),
                "metadata": ext_result.get("metadata", {}),
            })

    if not raw_texts:
        return {"success": False, "error": "No text content extracted from files", "record_count": 0}

    # Step 2: Chunk texts
    chunked = []
    for item in raw_texts:
        chunks = _chunk_text(item["text"], chunk_size, chunk_overlap)
        for chunk in chunks:
            if len(chunk.strip()) >= min_length:
                chunked.append({
                    "text": chunk.strip(),
                    "source": item["source"],
                    "file_type": item["file_type"],
                })

    # Step 3: Deduplicate
    if deduplicate:
        seen = set()
        deduped = []
        for item in chunked:
            h = hashlib.md5(item["text"].encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                deduped.append(item)
        chunked = deduped

    # Step 4: Format into target schema
    records = _format_records(chunked, output_format)

    if not records:
        return {"success": False, "error": "No records generated after formatting", "record_count": 0}

    # Step 5: Write output
    ext_map = {"jsonl": ".jsonl", "csv": ".csv", "parquet": ".parquet"}
    out_ext = ext_map.get(output_type, ".jsonl")
    output_path = os.path.join(output_dir, f"{dataset_name}{out_ext}")

    if output_type == "jsonl":
        _write_jsonl(records, output_path)
    elif output_type == "csv":
        _write_csv(records, output_path)
    elif output_type == "parquet":
        _write_parquet(records, output_path)
    else:
        _write_jsonl(records, output_path)

    file_size = os.path.getsize(output_path)

    # Quality stats
    total_chars = sum(len(r.get("text", r.get("instruction", ""))) for r in records)
    avg_len = total_chars // len(records) if records else 0

    return {
        "success": True,
        "output_path": output_path,
        "output_format": output_format,
        "output_type": output_type,
        "record_count": len(records),
        "file_size": file_size,
        "file_size_human": _format_size(file_size),
        "stats": {
            "total_sources": len(raw_texts),
            "chunks_before_dedup": len(chunked) + (len(raw_texts) - len(chunked) if deduplicate else 0),
            "chunks_after_dedup": len(chunked),
            "avg_record_length": avg_len,
            "total_characters": total_chars,
        },
        "sample": records[:3],
    }


# ── Formatters ──────────────────────────────────────────

def _format_records(chunks: list, format_type: str) -> list:
    """Convert raw chunks into the target dataset format."""
    records = []

    if format_type == "raw_text":
        for chunk in chunks:
            records.append({
                "text": chunk["text"],
                "source": chunk["source"],
            })

    elif format_type == "instruction":
        for chunk in chunks:
            records.append({
                "instruction": "Based on the following content, provide a summary or answer questions about it.",
                "input": chunk["text"],
                "output": "",  # To be filled by annotator or LLM
            })

    elif format_type == "chat":
        for chunk in chunks:
            records.append({
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant trained on proprietary data."},
                    {"role": "user", "content": chunk["text"]},
                    {"role": "assistant", "content": ""},  # To be completed
                ]
            })

    elif format_type == "classification":
        for chunk in chunks:
            records.append({
                "text": chunk["text"],
                "label": chunk.get("file_type", "unclassified"),
            })

    elif format_type == "qa":
        for chunk in chunks:
            records.append({
                "question": "",
                "answer": "",
                "context": chunk["text"],
            })

    elif format_type == "image_caption":
        for chunk in chunks:
            if chunk.get("file_type") == "image":
                records.append({
                    "image_path": chunk.get("source", ""),
                    "caption": chunk.get("text", ""),
                })

    return records


# ── Text Chunking ───────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list:
    """Split text into overlapping chunks at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > chunk_size and current:
            chunks.append(current.strip())
            # Overlap: keep last part of current chunk
            if overlap > 0:
                current = current[-overlap:] + " " + sentence
            else:
                current = sentence
        else:
            current = current + " " + sentence if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ── Writers ─────────────────────────────────────────────

def _write_jsonl(records: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_csv(records: list, path: str):
    import csv
    if not records:
        return
    keys = records[0].keys()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in records:
            # Flatten complex fields
            flat = {}
            for k, v in r.items():
                flat[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
            writer.writerow(flat)


def _write_parquet(records: list, path: str):
    try:
        import pandas as pd
        df = pd.DataFrame(records)
        df.to_parquet(path, index=False)
    except ImportError:
        # Fallback to JSONL
        _write_jsonl(records, path.replace(".parquet", ".jsonl"))


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
