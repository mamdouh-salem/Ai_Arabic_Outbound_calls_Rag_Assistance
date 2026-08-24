"""
outbound_ai.auth.models
=======================
Pydantic/dataclass models for the authentication layer.

These are pure value objects — no I/O, no DB calls, no FastAPI imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class AppRole(str, Enum):
    """Mirrors the Postgres `app_role` enum in 003_multi_tenancy.sql.

    Values are strings so they serialise transparently into JSON responses
    and compare cleanly against JWT claim strings.
    """

    super_admin = "super_admin"
    admin = "admin"
    agent = "agent"

    # Convenience helpers ---------------------------------------------------

    def is_super_admin(self) -> bool:
        return self is AppRole.super_admin

    def is_admin_or_above(self) -> bool:
        return self in (AppRole.admin, AppRole.super_admin)

    def can_manage_kb(self) -> bool:
        """Admins and super_admins may upload / delete KB documents."""
        return self.is_admin_or_above()

    def can_manage_users(self) -> bool:
        """Admins manage workspace users; super_admin manages everything."""
        return self.is_admin_or_above()


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Resolved identity injected into every authenticated FastAPI request.

    Created by ``auth.middleware.resolve_auth_context()`` and surfaced via
    the ``get_current_user`` dependency.  Treat as immutable.

    Attributes:
        user_id:      UUID matching ``auth.users.id`` in Supabase.
        workspace_id: UUID of the workspace the user is acting within.
                      ``None`` only for super_admin users who haven't been
                      scoped to a specific workspace.
        role:         The effective role for this request context.
        email:        User's email (from JWT ``email`` claim).
    """

    user_id: UUID
    workspace_id: UUID | None
    role: AppRole
    email: str

    def assert_workspace(self) -> UUID:
        """Return workspace_id or raise if the context is workspace-less.

        Use this inside route handlers that unconditionally need a workspace.
        Super admins operating at the platform level (e.g. billing API) call
        these routes with a workspace scoping header instead.
        """
        if self.workspace_id is None:
            raise ValueError(
                "AuthContext has no workspace_id. "
                "Super admin requests must supply an X-Workspace-Id header."
            )
        return self.workspace_id
