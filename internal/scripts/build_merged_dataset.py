#!/usr/bin/env python3
"""
Build the merged Magneto dataset: AEI text + AEI vision + Qwen3.7 reasoning + Fable-5 agent traces.
Output: datasets/train_magneto_merged.jsonl — ready for Unsloth multimodal training.
"""
import json, os
from pathlib import Path

SRC = Path(r"J:\NPU-STACK\datasets")
OUT = SRC / "train_magneto_merged.jsonl"

def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").strip().split("\n")]

SYSTEM_AEI = "You are Nirvana, the AI core of NPU-STACK, powered by Magneto. You serve Atmospheric Energy Inc. (AEI) providing technical advice on solar energy, battery storage, intelligent routing, and energy infrastructure. You analyze images, interpret data, and give precise, actionable answers."
SYSTEM_CODE = "You are Nirvana, a coding and agentic reasoning AI powered by NPU-STACK. You write clean, tested code, plan architectural decisions, and execute multi-step agentic workflows. You think step-by-step and verify your work."

normalized = []

# ── 1. AEI text entries (train.jsonl) ──
if (SRC / "train.jsonl").exists():
    for e in load_jsonl(SRC / "train.jsonl"):
        for m in e["messages"]:
            if isinstance(m.get("content"), str):
                m["content"] = [{"type": "text", "text": m["content"]}]
        normalized.append(e)
    print(f"  AEI text: {len(normalized)}")

# ── 2. AEI multimodal entries (train_multimodal.jsonl, entries 250-261) ──
multimodal_entries = load_jsonl(SRC / "train_multimodal.jsonl")
# Only take multimodal entries (entries with image in content)
mm_count = 0
for e in multimodal_entries:
    has_image = False
    for m in e["messages"]:
        if isinstance(m.get("content"), list):
            for p in m["content"]:
                if p.get("type") == "image":
                    has_image = True
    if has_image:
        for m in e["messages"]:
            if isinstance(m.get("content"), str):
                m["content"] = [{"type": "text", "text": m["content"]}]
        normalized.append(e)
        mm_count += 1
print(f"  AEI multimodal: {mm_count}")

# ── 3. Qwen3.7 Max Thinking → conversation format ──
qwen_file = SRC / "qwen3.7_max_thinking.jsonl"
if qwen_file.exists():
    qwen_count = 0
    for e in load_jsonl(qwen_file):
        problem = e.get("problem", "")
        trace = e.get("thinking_trace", "")
        answer = e.get("answer", "")
        if not problem or not answer:
            continue
        normalized.append({
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": SYSTEM_CODE}]},
                {"role": "user", "content": [{"type": "text", "text": f"Solve this problem step by step:\n\n{problem}"}]},
                {"role": "assistant", "content": [{"type": "text", "text": f"<think>\n{trace}\n</think>\n\n<answer>\n{answer}\n</answer>"}]},
            ]
        })
        qwen_count += 1
        if qwen_count >= 1000:  # Cap at 1K to keep dataset balanced
            break
    print(f"  Qwen3.7 reasoning: {qwen_count}")
else:
    print("  Qwen3.7: file not found — skipping")

# ── 4. Fable-5 agent traces → conversation format ──
fable_file = SRC / "fable5_cot_merged.jsonl"
if fable_file.exists():
    fable_count = 0
    for e in load_jsonl(fable_file):
        ctx = e.get("context", "")
        cot = e.get("cot", "")
        output = e.get("output", "")
        output_type = e.get("output_type", "text")
        if not ctx or not output:
            continue
        # Only keep tool_use rows (most valuable for agent training)
        if output_type != "tool_use":
            continue
        out_text = json.dumps(output) if isinstance(output, dict) else str(output)
        if len(ctx) > 4000:
            ctx = ctx[:4000] + "..."
        if len(cot) > 2000:
            cot = cot[:2000] + "..."
        normalized.append({
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": SYSTEM_CODE}]},
                {"role": "user", "content": [{"type": "text", "text": f"Task:\n{ctx}"}]},
                {"role": "assistant", "content": [{"type": "text", "text": f"<think>\n{cot}\n</think>\n\n<tool_call>\n{out_text}\n</tool_call>"}]},
            ]
        })
        fable_count += 1
        if fable_count >= 1000:
            break
    print(f"  Fable-5 agent: {fable_count}")
else:
    print("  Fable-5: file not found — skipping")

# ── Write ──
OUT.write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in normalized) + "\n",
    encoding="utf-8",
)
print(f"\nDataset written: {OUT}")
print(f"  Total entries: {len(normalized)}")
print(f"  AEI: {len(normalized) - min(mm_count + 1000 + 1000, mm_count + 2000)} text + {mm_count} vision")
print(f"  Qwen3.7: {min(1000, qwen_count if 'qwen_count' in dir() else 0)} reasoning")
print(f"  Fable-5: {min(1000, fable_count if 'fable_count' in dir() else 0)} agent")
