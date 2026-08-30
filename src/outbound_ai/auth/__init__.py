"""
outbound_ai.auth
================
Authentication and authorization primitives for the Arabic Outbound Call Agent.

Public surface:
    AuthContext       -- the resolved identity injected into every request
    AppRole           -- enum matching the Postgres app_role type
    get_current_user  -- FastAPI dependency: validates JWT, returns AuthContext
    require_role      -- dependency factory for role-gated routes
    require_super_admin    -- pre-built: super_admin only (platform-level: workspaces, users)
    require_admin_only     -- pre-built: admin only (workspace ops: KB, RAG, SQL)
    require_admin_or_agent -- pre-built: admin or agent (RAG chat co-pilot)
"""
from outbound_ai.auth.dependencies import (
    get_current_user,
    require_admin_only,
    require_admin_or_agent,
    require_role,
    require_super_admin,
)
from outbound_ai.auth.models import AppRole, AuthContext

__all__ = [
    "AppRole",
    "AuthContext",
    "get_current_user",
    "require_role",
    "require_super_admin",
    "require_admin_only",
    "require_admin_or_agent",
]
