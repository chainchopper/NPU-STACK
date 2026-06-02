"""Unified docs indexing and retrieval service for Nirvana orchestration.

Builds and persists a searchable document chunk index across local project docs
and selected external compatibility docs.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


try:
    import requests
except Exception:  # pragma: no cover - optional fallback
    requests = None


INDEX_VERSION = 1
MAX_FILE_BYTES = 1_500_000
MAX_CHARS_PER_DOC = 120_000
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180

_LOCK = threading.Lock()
_HIGHLIGHT_RE = re.compile(r"[A-Za-z0-9_\-\.]{2,}")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _data_dir() -> Path:
    data_dir = _project_root() / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _index_path() -> Path:
    return _data_dir() / "docs_index.json"


def _sync_status_path() -> Path:
    return _data_dir() / "docs_sync_status.json"


def _load_sync_status() -> Dict[str, Any]:
    path = _sync_status_path()
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _save_sync_status(payload: Dict[str, Any]) -> None:
    path = _sync_status_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _record_sync_status(sync_type: str, payload: Dict[str, Any]) -> None:
    current = _load_sync_status()
    current[sync_type] = {
        **payload,
        "recorded_at": _utc_iso(),
    }
    _save_sync_status(current)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_\-\.]{2,}", (text or "").lower())


def _safe_read_text(path: Path) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if len(data) > MAX_CHARS_PER_DOC:
        data = data[:MAX_CHARS_PER_DOC]
    return data.strip()


def _iter_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterable[str]:
    clean = (text or "").strip()
    if not clean:
        return
    start = 0
    step = max(1, size - overlap)
    while start < len(clean):
        end = min(len(clean), start + size)
        chunk = clean[start:end].strip()
        if chunk:
            yield chunk
        if end >= len(clean):
            break
        start += step


def _default_external_sources() -> List[Dict[str, str]]:
    return [
        {
            "id": "nirvana-llms",
            "url": "https://docs.nirvanalabs.ai/docs/llms.txt",
            "label": "Nirvana Docs (llms.txt)",
            "tags": "nirvana runtime llms",
        },
        {
            "id": "nirvana-llms-full",
            "url": "https://docs.nirvanalabs.ai/docs/llms-full.txt",
            "label": "Nirvana Docs (llms-full.txt)",
            "tags": "nirvana runtime llms",
        },
    ]


def _default_local_roots() -> List[Path]:
    root = _project_root()
    return [
        root / "README.md",
        root / "docs",
        root / "gitbook-npu-stack",
        root / "gitbook-clone" / "README.md",
        root / "backend",
        root / "frontend" / "src",
        root / "temp_unsloth_studio_inspect" / "studio" / "frontend" / "src",
    ]


def _is_allowed_file(path: Path) -> bool:
    allowed_suffixes = {
        ".md",
        ".txt",
        ".rst",
        ".json",
        ".yaml",
        ".yml",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".py",
    }
    if path.suffix.lower() not in allowed_suffixes:
        return False

    lowered = str(path).replace("\\", "/").lower()
    blocked_parts = [
        "/node_modules/",
        "/dist/",
        "/build/",
        "/.git/",
        "/__pycache__/",
        "/backend/data/models/",
        "/backend/data/uploads/",
    ]
    return not any(part in lowered for part in blocked_parts)


def _iter_local_docs() -> Iterable[Path]:
    for root in _default_local_roots():
        if not root.exists():
            continue
        if root.is_file():
            if _is_allowed_file(root):
                yield root
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if not _is_allowed_file(path):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


@dataclass
class _Chunk:
    id: str
    text: str
    source: str
    title: str
    source_type: str
    tags: List[str]


def _build_local_chunks() -> List[_Chunk]:
    project_root = _project_root()
    chunks: List[_Chunk] = []
    for path in _iter_local_docs():
        text = _safe_read_text(path)
        if not text:
            continue
        rel = path.relative_to(project_root).as_posix()
        title = path.name
        tags = _tokenize(rel)
        for idx, chunk_text in enumerate(_iter_chunks(text)):
            digest = hashlib.sha1(f"{rel}:{idx}:{chunk_text[:200]}".encode("utf-8")).hexdigest()[:16]
            chunks.append(
                _Chunk(
                    id=f"local-{digest}",
                    text=chunk_text,
                    source=rel,
                    title=title,
                    source_type="local",
                    tags=tags,
                )
            )
    return chunks


def _download_external_text(url: str, timeout: int = 12) -> str:
    if requests is None:
        return ""
    try:
        resp = requests.get(url, timeout=timeout)
        if not resp.ok:
            return ""
        text = (resp.text or "").strip()
        if len(text) > MAX_CHARS_PER_DOC:
            text = text[:MAX_CHARS_PER_DOC]
        return text
    except Exception:
        return ""


def _default_project_doc_sources() -> List[Dict[str, str]]:
    return [
        {
            "title": "Repository README",
            "source": "README.md",
            "destination": "resources/project-docs/repository-readme.md",
        },
        {
            "title": "Architecture Guide",
            "source": "docs/ARCHITECTURE.md",
            "destination": "resources/project-docs/architecture-guide.md",
        },
        {
            "title": "Backend Guide",
            "source": "docs/BACKEND.md",
            "destination": "resources/project-docs/backend-guide.md",
        },
        {
            "title": "Frontend Guide",
            "source": "docs/FRONTEND.md",
            "destination": "resources/project-docs/frontend-guide.md",
        },
        {
            "title": "Docker Guide",
            "source": "docs/DOCKER.md",
            "destination": "resources/project-docs/docker-guide.md",
        },
        {
            "title": "Advanced Training UI",
            "source": "docs/ADVANCED-TRAINING-UI.md",
            "destination": "resources/project-docs/advanced-training-ui.md",
        },
        {
            "title": "Runtime Compatibility Roadmap",
            "source": "docs/UNIFIED-RUNTIME-COMPATIBILITY-ROADMAP.md",
            "destination": "resources/project-docs/runtime-compatibility-roadmap.md",
        },
    ]


def _gitbook_root() -> Path:
    return _project_root() / "gitbook-npu-stack"


def _normalize_gitbook_target(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"^https?://", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip("/")


def _shared_gitbook_base_url() -> str:
    return (os.getenv("NPU_STACK_GITBOOK_BASE_URL") or "http://localhost:3001").strip().rstrip("/")


def _default_gitbook_projects() -> List[Dict[str, Any]]:
    raw = (os.getenv("NPU_STACK_GITBOOK_PROJECTS_JSON") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                projects: List[Dict[str, Any]] = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    project_id = str(item.get("id") or "").strip()
                    if not project_id:
                        continue
                    projects.append(
                        {
                            "id": project_id,
                            "title": str(item.get("title") or project_id).strip(),
                            "description": str(item.get("description") or "").strip(),
                            "published_url": _normalize_gitbook_target(str(item.get("published_url") or "")),
                            "local_root": str(item.get("local_root") or "").strip(),
                            "default": bool(item.get("default")),
                        }
                    )
                if projects:
                    return projects
        except Exception:
            pass

    return [
        {
            "id": "npu-stack",
            "title": "NPU-STACK",
            "description": "NPU-STACK docs routed through the shared GitBook renderer.",
            "published_url": _normalize_gitbook_target(
                os.getenv("NPU_STACK_GITBOOK_NPU_STACK_PUBLISHED_URL", "")
            ),
            "local_root": "gitbook-npu-stack",
            "default": True,
        }
    ]


def _resolve_gitbook_project(project_id: Optional[str] = None) -> Dict[str, Any]:
    projects = _default_gitbook_projects()
    current_project = (project_id or os.getenv("NPU_STACK_GITBOOK_CURRENT_PROJECT") or "").strip()

    if current_project:
        for project in projects:
            if project.get("id") == current_project:
                return project

    for project in projects:
        if project.get("default"):
            return project

    return projects[0] if projects else {}


def _resolve_project_local_root(project_id: Optional[str] = None) -> Optional[Path]:
    project = _resolve_gitbook_project(project_id)
    local_root = str(project.get("local_root") or "").strip()
    if not local_root:
        return None

    project_root = _project_root().resolve()
    resolved = (project_root / local_root).resolve()
    if not str(resolved).startswith(str(project_root)):
        return None
    return resolved


def get_gitbook_registry() -> Dict[str, Any]:
    base_url = _shared_gitbook_base_url()
    projects = _default_gitbook_projects()
    current_project = _resolve_gitbook_project().get("id")
    renderer_path_prefix = "/url"

    hydrated_projects: List[Dict[str, Any]] = []
    for project in projects:
        published_url = _normalize_gitbook_target(str(project.get("published_url") or ""))
        renderer_url = f"{base_url}{renderer_path_prefix}/{published_url}" if published_url else None
        local_root = str(project.get("local_root") or "").strip()
        local_root_exists = False
        if local_root:
            candidate = _resolve_project_local_root(project.get("id"))
            local_root_exists = bool(candidate and candidate.exists())

        hydrated_projects.append(
            {
                "id": project.get("id"),
                "title": project.get("title"),
                "description": project.get("description") or "",
                "published_url": published_url,
                "renderer_url": renderer_url,
                "embed_url": renderer_url,
                "configured": bool(published_url),
                "local_root": local_root or None,
                "local_root_exists": local_root_exists,
                "default": bool(project.get("default")),
            }
        )

    return {
        "enabled": True,
        "integration_mode": "shared-renderer",
        "base_url": base_url,
        "renderer_path_prefix": renderer_path_prefix,
        "current_project": current_project,
        "projects": hydrated_projects,
    }


def _safe_summary_entries(root: Optional[Path] = None) -> List[Dict[str, str]]:
    gitbook_root = (root or _gitbook_root()).resolve()
    summary = gitbook_root / "SUMMARY.md"
    if not summary.exists():
        return []

    entries: List[Dict[str, str]] = []
    line_re = re.compile(r"^\s*\*\s+\[(.*?)\]\((.*?)\)\s*$")
    for line in summary.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = line_re.match(line)
        if not m:
            continue
        title, rel_path = m.group(1).strip(), m.group(2).strip()
        if not rel_path.lower().endswith(".md"):
            continue
        entries.append({"title": title, "path": rel_path})
    return entries


def list_gitbook_docs(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    root = _resolve_project_local_root(project_id)
    if not root:
        return []

    entries = _safe_summary_entries(root)
    out: List[Dict[str, Any]] = []
    for entry in entries:
        rel_path = entry["path"].replace("\\", "/")
        abs_path = (root / rel_path).resolve()
        if not str(abs_path).startswith(str(root.resolve())):
            continue
        out.append(
            {
                "title": entry["title"],
                "path": rel_path,
                "exists": abs_path.exists(),
                "project_id": (_resolve_gitbook_project(project_id).get("id") or None),
            }
        )
    return out


def read_gitbook_doc(rel_path: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    project = _resolve_gitbook_project(project_id)
    root = _resolve_project_local_root(project_id)
    if not root:
        return {"error": "project has no local GitBook mirror", "project_id": project.get("id")}

    root = root.resolve()
    clean = (rel_path or "").strip().replace("\\", "/")
    if not clean:
        return {"error": "path required"}

    abs_path = (root / clean).resolve()
    if not str(abs_path).startswith(str(root)):
        return {"error": "invalid path"}
    if not abs_path.exists() or not abs_path.is_file():
        return {"error": "document not found", "path": clean}

    content = abs_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "title": abs_path.stem,
        "path": clean,
        "content": content,
        "project_id": project.get("id"),
    }


def sync_external_docs_to_gitbook(project_id: Optional[str] = None) -> Dict[str, Any]:
    project = _resolve_gitbook_project(project_id)
    root = _resolve_project_local_root(project_id)
    if not root or not root.exists():
        _record_sync_status(
            "external",
            {
                "status": "failed",
                "error": "project local GitBook mirror not found",
                "project_id": project.get("id"),
                "count": 0,
            },
        )
        return {
            "status": "failed",
            "error": "project local GitBook mirror not found",
            "project_id": project.get("id"),
        }

    docs_dir = root / "resources" / "runtime-compatibility"
    docs_dir.mkdir(parents=True, exist_ok=True)
    summary_path = root / "SUMMARY.md"
    summary_text = summary_path.read_text(encoding="utf-8", errors="ignore") if summary_path.exists() else ""

    written: List[Dict[str, str]] = []
    for source in _default_external_sources():
        text = _download_external_text(source["url"])
        if not text:
            continue
        out_name = f"{source['id']}.md"
        out_path = docs_dir / out_name
        body = (
            f"# {source['label']}\n\n"
            f"Source URL: {source['url']}\n\n"
            "---\n\n"
            f"```text\n{text}\n```\n"
        )
        out_path.write_text(body, encoding="utf-8")
        written.append({"id": source["id"], "path": f"resources/runtime-compatibility/{out_name}"})

    index_path = docs_dir / "index.md"
    lines = ["# Runtime Compatibility Docs", "", "Generated external runtime references:", ""]
    for item in written:
        file_name = item["path"].split("/", 2)[-1]
        lines.append(f"- [{item['id']}](./{file_name})")
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    section_header = "## Runtime Compatibility"
    section_line = "* [Runtime Compatibility Docs](resources/runtime-compatibility/index.md)"
    if section_line not in summary_text:
        append = "\n\n" + section_header + "\n\n" + section_line + "\n"
        summary_path.write_text(summary_text + append, encoding="utf-8")

    _record_sync_status(
        "external",
        {
            "status": "success",
            "project_id": project.get("id"),
            "count": len(written),
            "index": "resources/runtime-compatibility/index.md",
            "written": written,
        },
    )

    return {
        "status": "success",
        "written": written,
        "index": "resources/runtime-compatibility/index.md",
        "count": len(written),
        "project_id": project.get("id"),
    }


def sync_project_docs_to_gitbook(project_id: Optional[str] = None) -> Dict[str, Any]:
    project = _resolve_gitbook_project(project_id)
    root = _resolve_project_local_root(project_id)
    if not root or not root.exists():
        _record_sync_status(
            "project",
            {
                "status": "failed",
                "error": "project local GitBook mirror not found",
                "project_id": project.get("id"),
                "count": 0,
            },
        )
        return {
            "status": "failed",
            "error": "project local GitBook mirror not found",
            "project_id": project.get("id"),
        }

    project_root = _project_root().resolve()
    docs_dir = root / "resources" / "project-docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    written: List[Dict[str, str]] = []

    for doc in _default_project_doc_sources():
        source_rel = doc["source"]
        source_path = (project_root / source_rel).resolve()
        if not str(source_path).startswith(str(project_root)):
            continue
        if not source_path.exists() or not source_path.is_file():
            continue

        destination_rel = doc["destination"]
        destination_path = (root / destination_rel).resolve()
        if not str(destination_path).startswith(str(root.resolve())):
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        source_text = source_path.read_text(encoding="utf-8", errors="ignore").strip()
        body = (
            f"# {doc['title']}\n\n"
            f"Rebranded GitBook mirror of `{source_rel}` for the {project.get('title') or project.get('id') or 'project'} docs hub.\n\n"
            f"Source file: `{source_rel}`\n\n"
            "---\n\n"
            f"{source_text}\n"
        )
        destination_path.write_text(body, encoding="utf-8")
        written.append({
            "title": doc["title"],
            "source": source_rel,
            "path": destination_rel,
        })

    index_path = docs_dir / "index.md"
    lines = [
        "# Project Documentation",
        "",
        f"Curated project docs mirrored into GitBook for {project.get('title') or project.get('id') or 'this project'}.",
        "",
    ]
    for item in written:
        file_name = item["path"].split("/", 2)[-1]
        lines.append(f"- [{item['title']}](./{file_name})")
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_path = root / "SUMMARY.md"
    summary_text = summary_path.read_text(encoding="utf-8", errors="ignore") if summary_path.exists() else ""
    section_header = "## Project Documentation"
    section_line = "* [Project Documentation](resources/project-docs/index.md)"
    if section_line not in summary_text:
        append = "\n\n" + section_header + "\n\n" + section_line + "\n"
        summary_path.write_text(summary_text + append, encoding="utf-8")

    _record_sync_status(
        "project",
        {
            "status": "success",
            "project_id": project.get("id"),
            "count": len(written),
            "index": "resources/project-docs/index.md",
            "written": written,
        },
    )

    return {
        "status": "success",
        "written": written,
        "index": "resources/project-docs/index.md",
        "count": len(written),
        "project_id": project.get("id"),
    }


def _highlight_text(text: str, tokens: List[str]) -> str:
    if not text:
        return ""

    lowered_tokens = [t.lower() for t in tokens if len(t) >= 2]
    if not lowered_tokens:
        return html.escape(text)

    def repl(match: re.Match[str]) -> str:
        word = match.group(0)
        if word.lower() in lowered_tokens:
            return f"<mark>{html.escape(word)}</mark>"
        return html.escape(word)

    parts: List[str] = []
    cursor = 0
    for m in _HIGHLIGHT_RE.finditer(text):
        if m.start() > cursor:
            parts.append(html.escape(text[cursor:m.start()]))
        parts.append(repl(m))
        cursor = m.end()
    if cursor < len(text):
        parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _build_external_chunks() -> List[_Chunk]:
    chunks: List[_Chunk] = []
    for source in _default_external_sources():
        url = source["url"]
        text = _download_external_text(url)
        if not text:
            continue
        tags = _tokenize(source.get("tags") or "")
        for idx, chunk_text in enumerate(_iter_chunks(text)):
            digest = hashlib.sha1(f"{url}:{idx}:{chunk_text[:200]}".encode("utf-8")).hexdigest()[:16]
            chunks.append(
                _Chunk(
                    id=f"ext-{digest}",
                    text=chunk_text,
                    source=url,
                    title=source.get("label") or source.get("id") or "external-doc",
                    source_type="external",
                    tags=tags,
                )
            )
    return chunks


def _serialize_chunks(chunks: List[_Chunk]) -> List[Dict[str, Any]]:
    return [
        {
            "id": c.id,
            "text": c.text,
            "source": c.source,
            "title": c.title,
            "source_type": c.source_type,
            "tags": c.tags,
        }
        for c in chunks
    ]


def _index_stats(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    local_count = sum(1 for c in chunks if c.get("source_type") == "local")
    external_count = sum(1 for c in chunks if c.get("source_type") == "external")
    source_count = len({c.get("source") for c in chunks if c.get("source")})
    return {
        "chunks": len(chunks),
        "sources": source_count,
        "local_chunks": local_count,
        "external_chunks": external_count,
    }


def load_docs_index() -> Dict[str, Any]:
    path = _index_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_docs_index(index: Dict[str, Any]) -> None:
    path = _index_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_docs_index(force: bool = False, include_external: bool = True) -> Dict[str, Any]:
    with _LOCK:
        current = load_docs_index()
        if current and not force:
            return {
                "rebuilt": False,
                "reason": "existing index reused",
                "status": index_status(current),
            }

        started = time.time()
        chunks = _build_local_chunks()
        if include_external:
            chunks.extend(_build_external_chunks())

        serialized = _serialize_chunks(chunks)
        index = {
            "version": INDEX_VERSION,
            "built_at": _utc_iso(),
            "build_seconds": round(time.time() - started, 3),
            "sources": {
                "local_roots": [str(p) for p in _default_local_roots()],
                "external": _default_external_sources(),
                "include_external": include_external,
            },
            "stats": _index_stats(serialized),
            "chunks": serialized,
        }
        save_docs_index(index)
        return {
            "rebuilt": True,
            "reason": "index built",
            "status": index_status(index),
        }


def ensure_docs_index(max_age_seconds: int = 6 * 3600) -> Dict[str, Any]:
    current = load_docs_index()
    if not current:
        return build_docs_index(force=True, include_external=True)

    built_at = current.get("built_at")
    if not built_at:
        return build_docs_index(force=True, include_external=True)

    try:
        dt = datetime.fromisoformat(str(built_at))
        age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
        if age_seconds > max_age_seconds:
            return build_docs_index(force=True, include_external=True)
    except Exception:
        return build_docs_index(force=True, include_external=True)

    return {
        "rebuilt": False,
        "reason": "index fresh",
        "status": index_status(current),
    }


def index_status(index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = index or load_docs_index()
    chunks = data.get("chunks") or []
    stats = data.get("stats") or _index_stats(chunks)
    index_file = _index_path()
    return {
        "ready": bool(chunks),
        "version": data.get("version") or INDEX_VERSION,
        "built_at": data.get("built_at"),
        "build_seconds": data.get("build_seconds"),
        "index_file": str(index_file.resolve()),
        "index_file_exists": index_file.exists(),
        "stats": stats,
        "sync": _load_sync_status(),
        "sources": data.get("sources") or {
            "local_roots": [str(p) for p in _default_local_roots()],
            "external": _default_external_sources(),
            "include_external": True,
        },
    }


def search_docs(query: str, top_k: int = 6, source_type: Optional[str] = None) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    data = load_docs_index()
    chunks: List[Dict[str, Any]] = data.get("chunks") or []
    if not chunks:
        return []

    q_tokens = _tokenize(q)
    if not q_tokens:
        return []

    scored: List[tuple[float, Dict[str, Any]]] = []
    query_lower = q.lower()
    for chunk in chunks:
        if source_type and chunk.get("source_type") != source_type:
            continue
        text = (chunk.get("text") or "").lower()
        tags = " ".join(chunk.get("tags") or []).lower()
        title = (chunk.get("title") or "").lower()
        source = (chunk.get("source") or "").lower()

        score = 0.0
        for t in q_tokens:
            if t in text:
                score += 2.0
            if t in tags:
                score += 1.2
            if t in title:
                score += 2.5
            if t in source:
                score += 1.8
        if query_lower in text:
            score += 5.0
        if query_lower in title:
            score += 6.0
        if query_lower in source:
            score += 3.0

        # Source weighting: prefer curated docs over broad code snippets.
        source_path = (chunk.get("source") or "").replace("\\", "/").lower()
        if "/docs/" in source_path or source_path.startswith("docs/"):
            score += 1.8
        if "gitbook-npu-stack" in source_path:
            score += 2.2
        if "/backend/" in source_path and source_path.endswith(".py"):
            score -= 0.6
        if "/frontend/src/" in source_path and source_path.endswith((".js", ".jsx", ".ts", ".tsx")):
            score -= 0.3

        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    # Deduplicate near-identical snippets and limit repeats per source.
    results: List[Dict[str, Any]] = []
    seen_snippet_keys: set[str] = set()
    per_source_count: Dict[str, int] = {}

    for score, chunk in scored:
        source = chunk.get("source") or ""
        if per_source_count.get(source, 0) >= 2:
            continue

        snippet = (chunk.get("text") or "")[:500]
        snippet_key = hashlib.sha1(re.sub(r"\s+", " ", snippet.lower()).encode("utf-8")).hexdigest()[:14]
        if snippet_key in seen_snippet_keys:
            continue

        seen_snippet_keys.add(snippet_key)
        per_source_count[source] = per_source_count.get(source, 0) + 1

        results.append(
            {
                "score": round(score, 3),
                "id": chunk.get("id"),
                "source": source,
                "title": chunk.get("title"),
                "source_type": chunk.get("source_type"),
                "snippet": snippet,
                "snippet_highlighted": _highlight_text(snippet, q_tokens),
            }
        )

        if len(results) >= max(1, top_k):
            break

    return results


def format_docs_context(query: str, top_k: int = 5, max_chars: int = 4000) -> str:
    hits = search_docs(query, top_k=top_k)
    if not hits:
        return ""

    lines: List[str] = ["Relevant NPU-STACK compatibility docs context:"]
    for idx, hit in enumerate(hits, start=1):
        lines.append(
            f"[{idx}] {hit.get('title') or 'doc'} | {hit.get('source_type')} | {hit.get('source')}\n"
            f"{hit.get('snippet') or ''}"
        )

    out = "\n\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars]
    return out
