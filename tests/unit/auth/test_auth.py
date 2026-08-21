"""Unit tests for outbound_ai.auth.

Tests are designed to run with NO network access and NO Supabase instance.
All external calls (JWT decode, DB lookup) are mocked inline.
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

from outbound_ai.auth.middleware import (
    _JWT_ALGORITHM,
    _decode_jwt,
    _extract_bearer_token,
    resolve_auth_context,
)
from outbound_ai.auth.models import AppRole, AuthContext
from outbound_ai.auth.dependencies import require_role, get_current_user
from outbound_ai.config.settings import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JWT_SECRET = "test-super-secret-key-32-chars!!"  # 32+ chars for HS256

WORKSPACE_ID = uuid.uuid4()
USER_ID      = uuid.uuid4()


def _make_settings(secret: str = JWT_SECRET) -> Settings:
    """Build a minimal Settings object for auth tests."""
    from pydantic import SecretStr
    s = Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key=SecretStr("anon"),
        supabase_service_role_key=SecretStr("service"),
        supabase_jwt_secret=SecretStr(secret),
    )
    return s


def _make_token(
    sub: str | None = None,
    email: str = "agent@example.com",
    app_metadata: dict | None = None,
    exp_offset: int = 3600,
    secret: str = JWT_SECRET,
) -> str:
    payload = {
        "sub":   sub or str(USER_ID),
        "email": email,
        "iat":   int(time.time()),
        "exp":   int(time.time()) + exp_offset,
    }
    if app_metadata:
        payload["app_metadata"] = app_metadata
    return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)


def _make_request(token: str | None = None, workspace_header: str | None = None) -> MagicMock:
    """Create a mock FastAPI Request with an Authorization header."""
    req = MagicMock()
    headers: dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if workspace_header:
        headers["X-Workspace-Id"] = workspace_header
    req.headers = headers
    return req


# ===========================================================================
# 1. Token extraction
# ===========================================================================

class TestExtractBearerToken:
    def test_valid_bearer_token_extracted(self):
        req = _make_request(token="my.jwt.token")
        assert _extract_bearer_token(req) == "my.jwt.token"

    def test_missing_header_raises_401(self):
        req = MagicMock()
        req.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token(req)
        assert exc_info.value.status_code == 401

    def test_non_bearer_scheme_raises_401(self):
        req = MagicMock()
        req.headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token(req)
        assert exc_info.value.status_code == 401

    def test_bearer_without_token_raises_401(self):
        req = MagicMock()
        req.headers = {"Authorization": "Bearer "}
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token(req)
        assert exc_info.value.status_code == 401


# ===========================================================================
# 2. JWT decode
# ===========================================================================

class TestDecodeJwt:
    def test_valid_token_decoded(self):
        token    = _make_token()
        settings = _make_settings()
        payload  = _decode_jwt(token, settings)
        assert payload["sub"] == str(USER_ID)
        assert payload["email"] == "agent@example.com"

    def test_expired_token_raises_401(self):
        token    = _make_token(exp_offset=-1)  # expired 1 second ago
        settings = _make_settings()
        with pytest.raises(HTTPException) as exc_info:
            _decode_jwt(token, settings)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_wrong_secret_raises_401(self):
        token    = _make_token(secret="correct-secret-32-chars!!!!!!!!")
        settings = _make_settings(secret="wrong-secret-32-chars!!!!!!!!!")
        with pytest.raises(HTTPException) as exc_info:
            _decode_jwt(token, settings)
        assert exc_info.value.status_code == 401

    def test_malformed_token_raises_401(self):
        settings = _make_settings()
        with pytest.raises(HTTPException) as exc_info:
            _decode_jwt("not.a.real.jwt", settings)
        assert exc_info.value.status_code == 401

    def test_missing_jwt_secret_raises_500(self):
        token    = _make_token()
        settings = _make_settings()
        settings.__dict__["supabase_jwt_secret"] = None  # force None
        with pytest.raises(HTTPException) as exc_info:
            _decode_jwt(token, settings)
        assert exc_info.value.status_code == 500


# ===========================================================================
# 3. resolve_auth_context — super_admin path
# ===========================================================================

class TestResolveAuthContextSuperAdmin:
    @pytest.mark.asyncio
    async def test_super_admin_no_workspace_header(self):
        token    = _make_token(app_metadata={"platform_role": "super_admin"})
        settings = _make_settings()
        req      = _make_request(token=token)

        ctx = await resolve_auth_context(req, settings)

        assert ctx.role         == AppRole.super_admin
        assert ctx.user_id      == USER_ID
        assert ctx.workspace_id is None
        assert ctx.email        == "agent@example.com"

    @pytest.mark.asyncio
    async def test_super_admin_with_workspace_header(self):
        token    = _make_token(app_metadata={"platform_role": "super_admin"})
        settings = _make_settings()
        req      = _make_request(token=token, workspace_header=str(WORKSPACE_ID))

        ctx = await resolve_auth_context(req, settings)

        assert ctx.role         == AppRole.super_admin
        assert ctx.workspace_id == WORKSPACE_ID

    @pytest.mark.asyncio
    async def test_super_admin_bad_workspace_header_raises_400(self):
        token    = _make_token(app_metadata={"platform_role": "super_admin"})
        settings = _make_settings()
        req      = _make_request(token=token, workspace_header="not-a-uuid")

        with pytest.raises(HTTPException) as exc_info:
            await resolve_auth_context(req, settings)
        assert exc_info.value.status_code == 400


# ===========================================================================
# 4. resolve_auth_context — regular user path (DB mocked)
# ===========================================================================

def _mock_supabase_membership(workspace_id: uuid.UUID, role: str):
    """Returns a mock Supabase client that returns one workspace_members row."""
    mock_result = MagicMock()
    mock_result.data = [{"workspace_id": str(workspace_id), "role": role}]

    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value     = mock_table
    mock_table.limit.return_value  = mock_table
    mock_table.execute.return_value = mock_result

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table
    return mock_client


class TestResolveAuthContextRegularUser:
    @pytest.mark.asyncio
    async def test_agent_resolved(self):
        token    = _make_token()
        settings = _make_settings()
        req      = _make_request(token=token)

        with patch(
            "outbound_ai.auth.middleware._get_service_client",
            return_value=_mock_supabase_membership(WORKSPACE_ID, "agent"),
        ):
            ctx = await resolve_auth_context(req, settings)

        assert ctx.role         == AppRole.agent
        assert ctx.workspace_id == WORKSPACE_ID
        assert ctx.user_id      == USER_ID

    @pytest.mark.asyncio
    async def test_admin_resolved(self):
        token    = _make_token()
        settings = _make_settings()
        req      = _make_request(token=token)

        with patch(
            "outbound_ai.auth.middleware._get_service_client",
            return_value=_mock_supabase_membership(WORKSPACE_ID, "admin"),
        ):
            ctx = await resolve_auth_context(req, settings)

        assert ctx.role == AppRole.admin

    @pytest.mark.asyncio
    async def test_no_membership_raises_403(self):
        token    = _make_token()
        settings = _make_settings()
        req      = _make_request(token=token)

        mock_result        = MagicMock()
        mock_result.data   = []  # no rows → user has no workspace
        mock_table         = MagicMock()
        mock_table.select.return_value  = mock_table
        mock_table.eq.return_value      = mock_table
        mock_table.limit.return_value   = mock_table
        mock_table.execute.return_value = mock_result
        mock_client        = MagicMock()
        mock_client.table.return_value  = mock_table

        with patch(
            "outbound_ai.auth.middleware._get_service_client",
            return_value=mock_client,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_auth_context(req, settings)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_sub_in_token_raises_401(self):
        from pydantic import SecretStr
        # Manually craft a token without 'sub'
        payload = {"email": "x@x.com", "exp": int(time.time()) + 3600}
        token   = jwt.encode(payload, JWT_SECRET, algorithm=_JWT_ALGORITHM)
        settings = _make_settings()
        req      = _make_request(token=token)

        with pytest.raises(HTTPException) as exc_info:
            await resolve_auth_context(req, settings)
        assert exc_info.value.status_code == 401


# ===========================================================================
# 5. AppRole model helpers
# ===========================================================================

class TestAppRole:
    def test_super_admin_is_super_admin(self):
        assert AppRole.super_admin.is_super_admin()

    def test_admin_is_not_super_admin(self):
        assert not AppRole.admin.is_super_admin()

    def test_admin_is_admin_or_above(self):
        assert AppRole.admin.is_admin_or_above()

    def test_agent_is_not_admin_or_above(self):
        assert not AppRole.agent.is_admin_or_above()

    def test_super_admin_can_manage_kb(self):
        assert AppRole.super_admin.can_manage_kb()

    def test_agent_cannot_manage_kb(self):
        assert not AppRole.agent.can_manage_kb()


# ===========================================================================
# 6. require_role dependency factory
# ===========================================================================

class TestRequireRole:
    @pytest.mark.asyncio
    async def test_matching_role_passes(self):
        guard = require_role(AppRole.admin, AppRole.super_admin)
        ctx   = AuthContext(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            role=AppRole.admin,
            email="admin@example.com",
        )
        result = await guard(ctx)
        assert result is ctx

    @pytest.mark.asyncio
    async def test_non_matching_role_raises_403(self):
        guard = require_role(AppRole.admin, AppRole.super_admin)
        ctx   = AuthContext(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            role=AppRole.agent,
            email="agent@example.com",
        )
        with pytest.raises(HTTPException) as exc_info:
            await guard(ctx)
        assert exc_info.value.status_code == 403


# ===========================================================================
# 7. AuthContext.assert_workspace
# ===========================================================================

class TestAuthContextAssertWorkspace:
    def test_returns_workspace_id_when_set(self):
        ctx = AuthContext(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            role=AppRole.agent,
            email="x@x.com",
        )
        assert ctx.assert_workspace() == WORKSPACE_ID

    def test_raises_when_no_workspace(self):
        ctx = AuthContext(
            user_id=USER_ID,
            workspace_id=None,
            role=AppRole.super_admin,
            email="sa@x.com",
        )
        with pytest.raises(ValueError, match="no workspace_id"):
            ctx.assert_workspace()
