"""Docs index router — unified compatibility docs ingestion and retrieval."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.docs_index_service import build_docs_index
from services.docs_index_service import ensure_docs_index
from services.docs_index_service import get_gitbook_registry
from services.docs_index_service import index_status
from services.docs_index_service import list_gitbook_docs
from services.docs_index_service import read_gitbook_doc
from services.docs_index_service import search_docs
from services.docs_index_service import sync_external_docs_to_gitbook
from services.docs_index_service import sync_project_docs_to_gitbook


router = APIRouter(prefix="/api/docs-index", tags=["docs-index"])


class DocsIndexRebuildPayload(BaseModel):
    force: bool = True
    include_external: bool = True


class DocsSearchPayload(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    top_k: int = Field(default=6, ge=1, le=20)
    source_type: Optional[Literal["local", "external"]] = None


class GitBookDocPayload(BaseModel):
    path: str = Field(min_length=1, max_length=400)
    project_id: Optional[str] = Field(default=None, max_length=80)


class GitBookProjectPayload(BaseModel):
    project_id: Optional[str] = Field(default=None, max_length=80)


@router.get("/status")
def get_docs_index_status():
    return {
        "status": index_status(),
    }


@router.post("/ensure")
def ensure_index():
    return ensure_docs_index()


@router.post("/rebuild")
def rebuild_docs_index(payload: DocsIndexRebuildPayload):
    return build_docs_index(force=payload.force, include_external=payload.include_external)


@router.post("/search")
def search_docs_index(payload: DocsSearchPayload):
    results = search_docs(payload.query, top_k=payload.top_k, source_type=payload.source_type)
    return {
        "query": payload.query,
        "count": len(results),
        "results": results,
    }


@router.get("/gitbook/registry")
def get_gitbook_hosting_registry():
    return get_gitbook_registry()


@router.get("/gitbook/docs")
def get_gitbook_docs(project_id: Optional[str] = None):
    docs = list_gitbook_docs(project_id=project_id)
    return {
        "count": len(docs),
        "docs": docs,
    }


@router.post("/gitbook/read")
def read_gitbook_document(payload: GitBookDocPayload):
    data = read_gitbook_doc(payload.path, project_id=payload.project_id)
    if data.get("error"):
        return {
            "ok": False,
            **data,
        }
    return {
        "ok": True,
        **data,
    }


@router.post("/gitbook/sync-external")
def sync_gitbook_external_docs(payload: Optional[GitBookProjectPayload] = None):
    return sync_external_docs_to_gitbook(project_id=(payload.project_id if payload else None))


@router.post("/gitbook/sync-project")
def sync_gitbook_project_docs(payload: Optional[GitBookProjectPayload] = None):
    return sync_project_docs_to_gitbook(project_id=(payload.project_id if payload else None))
