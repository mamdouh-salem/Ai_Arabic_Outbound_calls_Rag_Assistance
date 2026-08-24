"""Workspace management — super_admin only.

POST /admin/workspaces          create a workspace
GET  /admin/workspaces          list all workspaces (+ member counts)
POST /admin/workspaces/{id}/members   put an existing user into a workspace with a role
"""
from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from outbound_ai.auth.dependencies import require_super_admin
from outbound_ai.auth.models import AuthContext
from outbound_ai.db.service_client import get_service_client

router = APIRouter(prefix="/admin/workspaces", tags=["workspaces"])

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=60,
                      description="URL-safe unique id, e.g. 'acme-telecom'")
    plan: Literal["free", "pro", "enterprise"] = "free"


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: Literal["admin", "agent"] = "agent"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    ctx: Annotated[AuthContext, Depends(require_super_admin)],
) -> dict:
    if not _SLUG_RE.match(body.slug):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Slug must be lowercase letters/digits separated by single dashes.",
        )
    sb = get_service_client()
    try:
        res = (
            sb.table("workspaces")
            .insert({"name": body.name, "slug": body.slug, "plan": body.plan})
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Workspace refused (slug taken?): {exc}"
        ) from exc
    return res.data[0]


@router.get("")
async def list_workspaces(
    ctx: Annotated[AuthContext, Depends(require_super_admin)],
) -> list[dict]:
    sb = get_service_client()
    workspaces = (sb.table("workspaces").select("*").execute().data) or []
    members = (sb.table("workspace_members").select("workspace_id, role").execute().data) or []
    counts: dict[str, int] = {}
    admins: dict[str, int] = {}
    for m in members:
        counts[m["workspace_id"]] = counts.get(m["workspace_id"], 0) + 1
        if m["role"] == "admin":
            admins[m["workspace_id"]] = admins.get(m["workspace_id"], 0) + 1
    return [
        {**ws, "members": counts.get(ws["id"], 0), "admins": admins.get(ws["id"], 0)}
        for ws in workspaces
    ]


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: uuid.UUID,
    body: AddMemberRequest,
    ctx: Annotated[AuthContext, Depends(require_super_admin)],
) -> dict:
    sb = get_service_client()
    try:
        res = (
            sb.table("workspace_members")
            .upsert(
                {"workspace_id": str(workspace_id), "user_id": str(body.user_id),
                 "role": body.role},
                on_conflict="workspace_id,user_id",
            )
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Membership refused: {exc}") from exc
    return res.data[0]


@router.get("/hierarchy/tree")
async def hierarchy_tree(
    ctx: Annotated[AuthContext, Depends(require_super_admin)],
) -> list[dict]:
    """Every workspace with its admins and the users beneath them — the
    platform org chart for super admins."""
    sb = get_service_client()
    workspaces = (sb.table("workspaces").select("id, name, slug, plan").execute().data) or []
    members = (
        sb.table("workspace_members")
        .select("workspace_id, user_id, role")
        .execute().data
    ) or []
    profiles = {
        u["id"]: u
        for u in (
            sb.table("users").select("id, email, display_name, platform_role").execute().data
            or []
        )
    }

    tree: dict[str, dict] = {}
    for m in members:
        ws = tree.setdefault(m["workspace_id"], {"admins": [], "agents": []})
        profile = profiles.get(m["user_id"], {"email": m["user_id"], "display_name": "?"})
        entry = {
            "user_id": m["user_id"],
            "email": profile.get("email"),
            "name": profile.get("display_name"),
            "workspace_role": m["role"],
        }
        bucket = "admins" if m["role"] == "admin" else "agents"
        ws[bucket].append(entry)

    return [
        {
            "workspace": w,
            "admins": tree.get(w["id"], {}).get("admins", []),
            "agents": tree.get(w["id"], {}).get("agents", []),
        }
        for w in workspaces
    ]
