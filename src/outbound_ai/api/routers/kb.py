"""KB document management API — admin/super_admin only.

POST   /kb/documents            upload a document (multipart file or JSON text)
GET    /kb/documents            list documents in a workspace (chunk counts)
DELETE /kb/documents/{source}   delete every chunk of one document

Agents are rejected at the dependency layer before any handler runs.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from outbound_ai.auth.dependencies import AdminOrAbove
from outbound_ai.auth.models import AuthContext
from outbound_ai.db.service_client import get_service_client
from outbound_ai.rag.ingestion import extract_text_from_pdf, ingest_document

router = APIRouter(prefix="/kb", tags=["kb"])

ALLOWED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


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
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if suffix == ".pdf":
            text = await asyncio.to_thread(extract_text_from_pdf, data)
        elif suffix in ALLOWED_TEXT_SUFFIXES:
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type '{suffix}'. Use .txt, .md or .pdf, or send raw content.",
            )
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
