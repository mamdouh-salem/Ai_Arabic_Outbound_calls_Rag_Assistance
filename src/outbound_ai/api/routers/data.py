"""Data visibility API — role-hierarchical access to tickets and calls.

Rules:
  agent       -> ONLY rows assigned to them (inside their workspace)
  admin       -> every row in their workspace
  super_admin -> everything; X-Workspace-Id header narrows to one workspace

The filter resolution lives in pure functions below so it's unit-testable
without a database.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from outbound_ai.auth.dependencies import CurrentUser
from outbound_ai.auth.models import AppRole, AuthContext
from outbound_ai.db.service_client import get_service_client

router = APIRouter(tags=["data"])


def visible_ticket_filters(ctx: AuthContext) -> dict[str, str] | None:
    """Supabase equality filters for tickets the caller may see.

    None means "no filter" (see everything). Raises ValueError when an
    admin/super_admin context lacks a workspace where one is required.
    """
    match ctx.role:
        case AppRole.agent:
            filters = {"assigned_to": str(ctx.user_id)}
            if ctx.workspace_id:
                filters["workspace_id"] = str(ctx.workspace_id)
            return filters
        case AppRole.admin:
            ws = ctx.assert_workspace()  # admins are always workspace-scoped
            return {"workspace_id": str(ws)}
        case _:
            # super_admin: scoped only when a header narrowed the context
            if ctx.workspace_id:
                return {"workspace_id": str(ctx.workspace_id)}
            return None


def visible_call_filters(
    ctx: AuthContext,
    *,
    fetch_assigned_ticket_ids: Any = None,
) -> dict[str, Any] | None:
    """Filters for calls visible to the caller.

    Agents have no direct column on calls — visibility derives from their
    assigned tickets, so the caller injects a lookup callable returning the
    caller's ticket ids (kept out of this function to stay DB-free).
    """
    match ctx.role:
        case AppRole.agent:
            ticket_ids = list(fetch_assigned_ticket_ids()) if fetch_assigned_ticket_ids else []
            if not ticket_ids:
                return {"ticket_id": ["__none__"]}  # matches nothing -> empty result
            return {"ticket_id": ticket_ids}
        case _:
            return visible_ticket_filters(ctx)


@router.get("/tickets")
async def list_tickets(ctx: CurrentUser) -> list[dict]:
    sb = get_service_client()
    query = sb.table("tickets").select("*")
    for column, value in (visible_ticket_filters(ctx) or {}).items():
        query = query.eq(column, value)
    res = query.execute()
    return res.data or []


@router.get("/calls")
async def list_calls(ctx: CurrentUser) -> list[dict]:
    sb = get_service_client()

    def assigned_ids() -> list[str]:
        q = sb.table("tickets").select("id").eq("assigned_to", str(ctx.user_id))
        if ctx.workspace_id:
            q = q.eq("workspace_id", str(ctx.workspace_id))
        return [row["id"] for row in (q.execute().data or [])]

    filters = visible_call_filters(ctx, fetch_assigned_ticket_ids=assigned_ids)
    if filters is None:
        res = sb.table("calls").select("*").execute()
        return res.data or []

    query = sb.table("calls").select("*")
    for column, value in filters.items():
        if isinstance(value, list):
            query = query.in_(column, value)
        else:
            query = query.eq(column, value)
    res = query.execute()
    return res.data or []
