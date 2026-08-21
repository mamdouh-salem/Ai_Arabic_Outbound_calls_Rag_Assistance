"""
outbound_ai.auth.middleware
============================
Core JWT validation and identity resolution for the Arabic Outbound Call Agent.

Flow (per request):
  1. Extract the Bearer token from the Authorization header.
  2. Decode + verify the Supabase-issued JWT (HS256 via SUPABASE_JWT_SECRET).
  3. If platform_role == 'super_admin' (in app_metadata), resolve workspace from
     an optional X-Workspace-Id header — return AuthContext with None workspace
     if the header is absent (platform-level requests are valid without one).
  4. For all other users, look up workspace_members to get (workspace_id, role).
  5. Return an AuthContext; raise HTTP 401/403 on any failure.

Design notes:
  • jose.jwt is used instead of PyJWT because it handles both HS256 and RS256
    without extra configuration surface, and is already used by supabase-py
    internally.
  • The workspace_members lookup uses the Supabase service-role client so it
    can read the table regardless of the caller's RLS policies.
  • Errors are logged with structlog, never leaked to the client.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, Request, status
from jose import ExpiredSignatureError, JWTError, jwt
from supabase import Client, create_client

from outbound_ai.auth.models import AppRole, AuthContext
from outbound_ai.config.settings import Settings

log = structlog.get_logger(__name__)

# Supabase JWT algorithm — HS256 by default.  Change to "RS256" if you've
# configured asymmetric signing in your Supabase project settings.
_JWT_ALGORITHM = "HS256"

# Claim key inside the JWT where Supabase stores server-set metadata
# (cannot be forged by the client — unlike user_metadata).
_APP_METADATA_CLAIM = "app_metadata"
_PLATFORM_ROLE_CLAIM = "platform_role"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def resolve_auth_context(
    request: Request,
    settings: Settings,
) -> AuthContext:
    """Extract, validate, and resolve the caller's identity from the JWT.

    Args:
        request:  The incoming FastAPI/Starlette Request object.
        settings: App settings, used to read SUPABASE_JWT_SECRET etc.

    Returns:
        A fully resolved AuthContext.

    Raises:
        HTTP 401 — missing / malformed / expired token.
        HTTP 403 — token is valid but user has no workspace membership
                   and is not a super_admin.
    """
    raw_token = _extract_bearer_token(request)
    payload   = _decode_jwt(raw_token, settings)
    return await _build_auth_context(request, payload, settings)


# ---------------------------------------------------------------------------
# Step 1: token extraction
# ---------------------------------------------------------------------------

def _extract_bearer_token(request: Request) -> str:
    """Pull the Bearer token from the Authorization header.

    Raises HTTP 401 if the header is absent or not in "Bearer <token>" form.
    """
    auth_header: str | None = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


# ---------------------------------------------------------------------------
# Step 2: JWT decode + verification
# ---------------------------------------------------------------------------

def _decode_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Verify the Supabase JWT signature and decode the payload.

    Raises HTTP 401 for any JWT error (expired, invalid signature, malformed).
    """
    if not settings.supabase_jwt_secret:
        log.error("jwt_secret_not_configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth configuration error.",
        )

    secret = settings.supabase_jwt_secret.get_secret_value()

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALGORITHM],
            # Supabase sets audience to "authenticated" for user JWTs.
            # Set options={"verify_aud": False} only if you use custom audiences.
            options={"verify_aud": False},
        )
    except ExpiredSignatureError:
        log.warning("jwt_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        log.warning("jwt_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ---------------------------------------------------------------------------
# Step 3+4: identity resolution
# ---------------------------------------------------------------------------

async def _build_auth_context(
    request: Request,
    payload: dict[str, Any],
    settings: Settings,
) -> AuthContext:
    """Resolve the JWT claims into a typed AuthContext.

    For super_admin: workspace_id is taken from X-Workspace-Id header (optional).
    For everyone else: workspace_id + role come from the workspace_members table.
    """
    raw_user_id: str | None = payload.get("sub")
    email: str = payload.get("email", "")

    if not raw_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(raw_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in token.",
        )

    # Check platform_role from app_metadata (server-set, cannot be spoofed)
    app_meta: dict[str, Any] = payload.get(_APP_METADATA_CLAIM) or {}
    raw_platform_role: str | None = app_meta.get(_PLATFORM_ROLE_CLAIM)

    if raw_platform_role == AppRole.super_admin.value:
        # Super admins bypass workspace RLS; resolve optional scoping header
        workspace_id = _resolve_optional_workspace_header(request)
        log.info(
            "auth_resolved_super_admin",
            user_id=str(user_id),
            workspace_id=str(workspace_id) if workspace_id else None,
        )
        return AuthContext(
            user_id=user_id,
            workspace_id=workspace_id,
            role=AppRole.super_admin,
            email=email,
        )

    # Regular user: look up workspace membership
    workspace_id, role = await _lookup_workspace_membership(user_id, settings)

    log.info(
        "auth_resolved",
        user_id=str(user_id),
        workspace_id=str(workspace_id),
        role=role.value,
    )
    return AuthContext(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        email=email,
    )


def _resolve_optional_workspace_header(request: Request) -> UUID | None:
    """Read the X-Workspace-Id header if present.  Returns None if absent."""
    raw: str | None = request.headers.get("X-Workspace-Id")
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Workspace-Id header is not a valid UUID.",
        )


async def _lookup_workspace_membership(
    user_id: UUID,
    settings: Settings,
) -> tuple[UUID, AppRole]:
    """Query workspace_members for the user's active workspace and role.

    Uses the service-role key so this read bypasses RLS (the middleware
    runs before any user-level policies apply).

    Raises HTTP 403 if the user has no workspace membership.
    """
    sb: Client = _get_service_client(settings)

    try:
        result = (
            sb.table("workspace_members")
            .select("workspace_id, role")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("workspace_lookup_failed", user_id=str(user_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        )

    rows = result.data
    if not rows:
        log.warning("no_workspace_membership", user_id=str(user_id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any workspace.",
        )

    row = rows[0]
    try:
        workspace_id = UUID(row["workspace_id"])
        role = AppRole(row["role"])
    except (ValueError, KeyError) as exc:
        log.error("workspace_row_parse_error", row=row, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth data integrity error.",
        )

    return workspace_id, role


# ---------------------------------------------------------------------------
# Supabase service-role client (singleton per process)
# ---------------------------------------------------------------------------
_sb_service_client: Client | None = None


def _get_service_client(settings: Settings) -> Client:
    """Lazily create a Supabase service-role client (process-singleton)."""
    global _sb_service_client  # noqa: PLW0603
    if _sb_service_client is None:
        if not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured.")
        _sb_service_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
        )
    return _sb_service_client
