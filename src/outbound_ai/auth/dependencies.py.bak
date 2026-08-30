"""
outbound_ai.auth.dependencies
==============================
FastAPI dependency functions for authentication and role enforcement.

Usage in route handlers:
    from outbound_ai.auth import get_current_user, require_admin_or_above, AuthContext
    from typing import Annotated
    from fastapi import Depends

    # Basic auth — any authenticated workspace user
    @router.get("/tickets")
    async def list_tickets(ctx: Annotated[AuthContext, Depends(get_current_user)]):
        ...

    # Role-gated — admin or super_admin only
    @router.post("/kb/documents")
    async def upload_document(
        ctx: Annotated[AuthContext, Depends(require_admin_or_above)],
    ):
        ...

    # Custom role gate — super_admin only
    @router.get("/platform/metrics")
    async def platform_metrics(
        ctx: Annotated[AuthContext, Depends(require_super_admin)],
    ):
        ...

    # One-off custom gate
    @router.delete("/workspaces/{workspace_id}")
    async def delete_workspace(
        ctx: Annotated[AuthContext, Depends(require_role(AppRole.super_admin))],
    ):
        ...
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status

from outbound_ai.auth.middleware import resolve_auth_context
from outbound_ai.auth.models import AppRole, AuthContext
from outbound_ai.config.settings import Settings, get_settings

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Core dependency: get_current_user
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    """FastAPI dependency that validates the JWT and returns an AuthContext.

    Raises:
        HTTP 401 — missing / invalid / expired Bearer token.
        HTTP 403 — valid token but user has no workspace membership.
    """
    return await resolve_auth_context(request, settings)


# Type alias for cleaner handler signatures
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Role enforcement factories
# ---------------------------------------------------------------------------

def require_role(*allowed_roles: AppRole):
    """Dependency factory that gates a route to specific roles.

    Example:
        @router.post("/admin/something")
        async def handler(ctx: Annotated[AuthContext, Depends(require_role(AppRole.admin, AppRole.super_admin))]):
            ...

    Args:
        *allowed_roles: One or more AppRole values permitted to access the route.

    Returns:
        A FastAPI dependency (async callable) that returns the AuthContext
        if the user's role is in allowed_roles, otherwise raises HTTP 403.
    """
    allowed_set = frozenset(allowed_roles)

    async def _enforce(ctx: CurrentUser) -> AuthContext:  # type: ignore[valid-type]
        if ctx.role not in allowed_set:
            log.warning(
                "access_denied",
                user_id=str(ctx.user_id),
                user_role=ctx.role.value,
                required_roles=[r.value for r in allowed_set],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires one of: "
                    f"{', '.join(r.value for r in sorted(allowed_set, key=lambda r: r.value))}. "
                    f"Your role is '{ctx.role.value}'."
                ),
            )
        return ctx

    # Give the inner function a meaningful name for OpenAPI docs + debugging
    _enforce.__name__ = f"require_role({'|'.join(r.value for r in allowed_set)})"
    return _enforce


# ---------------------------------------------------------------------------
# Pre-built role guards (cover ~90% of use-cases)
# ---------------------------------------------------------------------------

require_super_admin = require_role(AppRole.super_admin)
"""Dependency: super_admin only. Use for platform-level operations."""

require_admin_or_above = require_role(AppRole.admin, AppRole.super_admin)
"""Dependency: admin or super_admin. Use for workspace management, KB uploads."""

require_any_role = require_role(AppRole.agent, AppRole.admin, AppRole.super_admin)
"""Dependency: any authenticated workspace member. Equivalent to get_current_user
   but reads more clearly in route definitions that explicitly intend open access."""

# Typed aliases for handler signatures
SuperAdmin       = Annotated[AuthContext, Depends(require_super_admin)]
AdminOrAbove     = Annotated[AuthContext, Depends(require_admin_or_above)]
AnyAuthenticatedUser = Annotated[AuthContext, Depends(require_any_role)]
