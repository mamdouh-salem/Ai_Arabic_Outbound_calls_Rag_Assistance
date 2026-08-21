"""User management API — hierarchical authority model.

Authority rules (as specified by product owner):
  super_admin -> creates users of ANY role (admins included), sees everyone
  admin       -> sees users in their own workspace only
  agent       -> no access to any management endpoint (403 at dependency layer)
"""
from __future__ import annotations

import secrets
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from outbound_ai.auth.dependencies import AdminOrAbove, require_super_admin
from outbound_ai.auth.models import AppRole, AuthContext
from outbound_ai.db.service_client import get_service_client

router = APIRouter(prefix="/admin/users", tags=["user-management"])


class CreateUserRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["agent", "admin", "super_admin"]
    # Workspace to place the user in. Required for admin/agent; optional for
    # super_admin (platform-level accounts may be workspace-less).
    workspace_id: uuid.UUID | None = None
    password: str | None = Field(
        default=None,
        min_length=8,
        description="Omit to auto-generate one (returned ONCE in the response).",
    )


class CreatedUserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    platform_role: str
    workspace_id: str | None
    generated_password: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedUserResponse)
async def create_user(body: CreateUserRequest, ctx: Annotated[AuthContext, Depends(require_super_admin)]) -> dict:
    """Create a Supabase auth account + profile + (optional) workspace membership.

    super_admin only. If `password` is omitted a strong one is generated and
    returned exactly once — it cannot be retrieved later."""
    sb = get_service_client()

    if body.role in ("admin", "agent") and body.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role '{body.role}' requires a workspace_id.",
        )

    password = body.password or secrets.token_urlsafe(12)

    try:
        created = sb.auth.admin.create_user(
            {
                "email": body.email,
                "password": password,
                "email_confirm": True,  # admin-created users skip confirmation flow
                "user_metadata": {"display_name": body.display_name},
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supabase Auth refused user creation: {exc}",
        ) from exc

    user_id = created.user.id

    try:
        (
            sb.table("users")
            .upsert(
                {
                    "id": user_id,
                    "email": body.email,
                    "display_name": body.display_name,
                    "platform_role": body.role,
                },
                on_conflict="id",
            )
            .execute()
        )
        if body.workspace_id is not None:
            (
                sb.table("workspace_members")
                .upsert(
                    {
                        "workspace_id": str(body.workspace_id),
                        "user_id": user_id,
                        "role": body.role,
                    },
                    on_conflict="workspace_id,user_id",
                )
                .execute()
            )
    except Exception as exc:
        # Auth account exists but profile failed — flag loudly; don't leave
        # a silent half-created identity.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auth user {user_id} created but profile write failed: {exc}",
        ) from exc

    return {
        "user_id": user_id,
        "email": body.email,
        "display_name": body.display_name,
        "platform_role": body.role,
        "workspace_id": str(body.workspace_id) if body.workspace_id else None,
        "generated_password": password if body.password is None else None,
    }


@router.get("")
async def list_users(ctx: AdminOrAbove) -> list[dict]:
    """Users visible to the caller per the hierarchy:
    super_admin -> all users (optionally ?workspace_id=...); admin -> own workspace."""
    sb = get_service_client()
    role = ctx.role

    if role == AppRole.super_admin:
        res = sb.table("users").select("id, email, display_name, platform_role").execute()
        rows = res.data or []
    elif role == AppRole.admin:
        ws = ctx.assert_workspace()
        members = (
            sb.table("workspace_members")
            .select("user_id")
            .eq("workspace_id", str(ws))
            .execute()
        )
        ids = [m["user_id"] for m in members.data or []]
        rows = []
        for uid in ids:  # small workspaces; batch via .in_ when this grows
            r = (
                sb.table("users")
                .select("id, email, display_name, platform_role")
                .eq("id", uid)
                .limit(1)
                .execute()
            )
            rows.extend(r.data or [])
    else:  # defensive — dependency already blocks agents
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agents cannot list users.")

    return rows


@router.patch("/{user_id}/platform-role")
async def change_platform_role(
    user_id: uuid.UUID,
    new_role: Literal["agent", "admin", "super_admin"],
    ctx: Annotated[AuthContext, Depends(require_super_admin)],
) -> dict:
    """Promote/demote a user's PLATFORM role. super_admin only."""
    sb = get_service_client()
    res = (
        sb.table("users")
        .update({"platform_role": new_role})
        .eq("id", str(user_id))
        .select("id, email, platform_role")
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return {"status": "updated", **rows[0]}
