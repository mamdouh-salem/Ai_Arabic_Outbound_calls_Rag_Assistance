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


DEFAULT_WORKSPACE_ID = "aaaaaaaa-0000-0000-0000-000000000001"


def _require_workspace(ctx: AuthContext) -> str:
    """Workspace scoping for KB operations.

    admins act inside their own workspace; a super admin WITHOUT an explicit
    X-Workspace-Id scope defaults to the shared MAIN workspace (the platform
    knowledge base) — that's where platform-wide docs belong.
    """
    try:
        return str(ctx.assert_workspace())
    except ValueError:
        return DEFAULT_WORKSPACE_ID


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
    persona: str = "default"
    # arabic (default) | english | spanish | german | french
    language: str | None = None


def _chat_scope(ctx: AuthContext) -> tuple[list[str] | None, str]:
    """Workspace scoping for RAG retrieval.

    Returns (workspace_ids, label):
      agent       -> [own workspace]
      admin       -> [own workspace + the shared main KB]
      super_admin -> None (everything)
    """
    try:
        own = str(ctx.assert_workspace())
    except ValueError:
        return None, "ALL"
    if ctx.role == "admin":
        ids = [own]
        if own != DEFAULT_WORKSPACE_ID:
            ids.append(DEFAULT_WORKSPACE_ID)
        return ids, f"{own} + main KB"
    return [own], own


@router.post("/chat")
async def rag_chat(body: ChatRequest, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Ask the knowledge base a question; get a grounded answer with citations.
    Agents use this as their live-call co-pilot.

    persona selects the response style (default / egyptian_friendly / formal /
    concise / empathetic / technical); language forces the answer language
    (arabic / english / spanish / german / french)."""
    scope_ids, scope_label = _chat_scope(ctx)

    result = await asyncio.to_thread(
        generate_answer, body.question, body.category, scope_ids, "qa", "",
        body.persona, body.language,
    )
    return {
        "answer": result["answer"],
        "citations": result["citations"],
        "sources": result["sources"],
        "chunks_used": result["chunks_used"],
        "persona": body.persona,
        "language": body.language or "arabic",
        "workspace_scope": scope_label,
    }


@router.post("/chat/voice")
async def rag_chat_voice(
    ctx: AuthContext = Depends(get_current_user),
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    persona: str = Form(default="default"),
    language: str | None = Form(default=None),
) -> dict:
    """Voice round-trip with the RAG assistant:
    upload recorded speech → STT (Gemini) → RAG answer → TTS (ElevenLabs).
    Returns the text answer + citations + a URL to the spoken reply."""
    from outbound_ai.voice.voice_services import synthesize_to_cache, transcribe_audio_bytes

    data = await file.read()
    mime = file.content_type or "audio/mpeg"
    question = await asyncio.to_thread(transcribe_audio_bytes, data, mime)
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Could not understand the recording — try again.")

    scope_ids, scope_label = _chat_scope(ctx)
    result = await asyncio.to_thread(
        generate_answer, question, category, scope_ids, "qa", "", persona, language
    )

    audio_path = await synthesize_to_cache(result["answer"], prefix="chat")
    return {
        "question": question,
        "answer": result["answer"],
        "citations": result["citations"],
        "sources": result["sources"],
        "persona": persona,
        "language": language or "arabic",
        "workspace_scope": scope_label,
        "audio_url": f"/audio/{audio_path.name}" if audio_path else None,
    }
