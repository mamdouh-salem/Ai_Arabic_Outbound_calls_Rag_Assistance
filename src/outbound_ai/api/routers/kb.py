"""KB management + RAG chat API.

POST   /kb/documents            upload a document (admin/super_admin)
GET    /kb/documents            list documents in a workspace (admin/super_admin)
DELETE /kb/documents/{source}   delete every chunk of one document (admin+)
POST   /kb/chat                 RAG assistant with citations (any authenticated role)
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from outbound_ai.auth.dependencies import AdminOrAbove
from outbound_ai.auth.dependencies import get_current_user
from outbound_ai.auth.models import AuthContext
from outbound_ai.db.service_client import get_service_client
from outbound_ai.rag.ingestion import extract_text, ingest_document
from outbound_ai.rag.generation import generate_answer

router = APIRouter(prefix="/kb", tags=["kb"])


def _require_workspace(ctx: AuthContext) -> str:
    """Workspace scoping for KB operations.

    admins act inside their own workspace; super_admins must supply
    X-Workspace-Id when operating platform-wide.
    """
    try:
        return str(ctx.assert_workspace())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="super_admin must send an X-Workspace-Id header for KB operations.",
        ) from exc


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    ctx: AdminOrAbove,
    category: str = Form(...),
    file: UploadFile | None = File(default=None),
    title: str | None = Form(default=None),
    content: str | None = Form(default=None),
) -> dict:
    """Upload one KB document. Either attach a file (.txt/.md/.pdf) or pass
    raw `content` text. The document is chunked, embedded, and stored scoped
    to the caller's workspace."""
    workspace_id = _require_workspace(ctx)
    source_name = title or (file.filename if file and file.filename else "untitled")

    if file is not None and file.filename:
        data = await file.read()
        try:
            text = await asyncio.to_thread(extract_text, file.filename, data)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
            ) from exc
    elif content:
        text = content
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either a file or non-empty 'content'.",
        )

    result = await asyncio.to_thread(
        ingest_document,
        text,
        source_name=source_name,
        category=category,
        workspace_id=workspace_id,
    )
    if result["chunks"] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document produced no chunks (empty content?).",
        )
    return {"status": "ingested", **result, "category": category}


@router.get("/documents")
async def list_documents(ctx: AdminOrAbove) -> list[dict]:
    """List distinct documents (by source name) with chunk counts.

    super_admins without an X-Workspace-Id header see ALL workspaces' docs;
    otherwise listing is scoped to the resolved workspace."""
    sb = get_service_client()

    query = sb.table("knowledge_base_chunks").select("id, metadata")
    try:
        workspace_id = ctx.assert_workspace()
        query = query.eq("workspace_id", str(workspace_id))
    except ValueError:
        pass  # super_admin, platform-wide listing

    res = query.execute()
    docs: dict[str, dict] = {}
    for row in res.data or []:
        meta = row.get("metadata") or {}
        name = meta.get("source", "unknown")
        entry = docs.setdefault(name, {"source": name, "chunks": 0})
        entry["chunks"] += 1
        if meta.get("category") and "category" not in entry:
            entry["category"] = meta["category"]
    return sorted(docs.values(), key=lambda d: d["source"])


@router.delete("/documents/{source_name}")
async def delete_document(source_name: str, ctx: AdminOrAbove) -> dict:
    workspace_id = _require_workspace(ctx)
    sb = get_service_client()
    res = (
        sb.table("knowledge_base_chunks")
        .delete()
        .eq("workspace_id", workspace_id)
        .filter("metadata->>source", "eq", source_name)
        .execute()
    )
    deleted = len(res.data) if res.data else 0
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No document named '{source_name}' in this workspace.",
        )
    return {"status": "deleted", "source": source_name, "chunks_deleted": deleted}


# ---------------------------------------------------------------------------
# RAG assistant (the CSR co-pilot) — any authenticated user
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    category: str | None = None


@router.post("/chat")
async def rag_chat(body: ChatRequest, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Ask the knowledge base a question; get a grounded Arabic answer with
    citations. Agents use this as their live-call co-pilot.

    Visibility follows the same rules as data endpoints: agents query only
    their workspace; admins their own; super admins everything (or narrowed
    via X-Workspace-Id)."""
    try:
        workspace_id = ctx.assert_workspace()
        scope = str(workspace_id)
    except ValueError:
        scope = None  # platform-wide super_admin

    result = await asyncio.to_thread(
        generate_answer, body.question, body.category, scope
    )
    return {
        "answer": result["answer"],
        "citations": result["citations"],
        "sources": result["sources"],
        "chunks_used": result["chunks_used"],
        "workspace_scope": scope or "ALL",
    }
