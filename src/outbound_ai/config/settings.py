"""Central configuration, loaded from the environment / .env file.

Every module reads configuration through `get_settings()` and never touches os.environ
directly. Secrets are wrapped in SecretStr so they cannot leak into logs or tracebacks.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/outbound_ai/config/settings.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- LLM (OpenAI)
    openai_api_key: SecretStr | None = None
    openai_call_model: str = "gpt-4o-mini"
    openai_reasoning_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dim: int = 3072

    # ------------------------------------------------------------------------ STT
    stt_model: str = "gpt-4o-transcribe"
    stt_language: str = "ar"
    # Clips shorter than this are treated as an accidental button tap, not a turn.
    stt_min_audio_ms: int = 300

    # ------------------------------------------------------------------------ TTS
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    elevenlabs_quality_model_id: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "pcm_16000"
    audio_cache_dir: Path = Path("audio_cache")

    # ------------------------------------------------------------------- Database
    supabase_url: str = ""
    supabase_anon_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    database_url: SecretStr | None = None

    # -------------------------------------------------------------- Observability
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "outbound-ai-arabic"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ------------------------------------------------------------------ Telephony
    telephony_provider: Literal["simulated", "twilio"] = "simulated"
    twilio_account_sid: str = ""
    twilio_auth_token: SecretStr | None = None
    twilio_from_number: str = ""
    public_webhook_base_url: str = ""

    # ------------------------------------------------------------------------ App
    app_env: str = "dev"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    gradio_port: int = 7860

    # ----------------------------------------------------------------- RAG tuning
    rag_top_k_dense: int = 20
    rag_top_k_sparse: int = 20
    rag_rrf_k: int = 60
    rag_top_n_after_rerank: int = 5
    rag_min_grounding_score: float = Field(default=0.7, ge=0.0, le=1.0)

    # --------------------------------------------------------------------- Derived
    @property
    def audio_cache_path(self) -> Path:
        path = self.audio_cache_dir
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. Call `get_settings.cache_clear()` in tests to reload."""
    return Settings()
