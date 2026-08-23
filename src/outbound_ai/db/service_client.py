"""Process-singleton Supabase client factory.

service key  -> bypasses RLS; for admin operations and API-layer filtering.
               Only ever used server-side, never exposed to a client.
"""
from __future__ import annotations

from supabase import Client, create_client

from outbound_ai.config.settings import get_settings

_service_client: Client | None = None


def get_service_client() -> Client:
    """Lazily create the Supabase service-role client (one per process)."""
    global _service_client
    if _service_client is None:
        settings = get_settings()
        if not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured.")
        _service_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
        )
    return _service_client
