"""Central configuration, loaded from the environment / .env file.

Every module reads configuration through get_settings() and never touches os.environ
directly. Secrets are wrapped in SecretStr so they cannot leak into logs or tracebacks.
"""
from __future__ import annotations

import os
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
        populate_by_name=True,
    )

    # ---------------------------------------------------------------- LLM (OpenAI)
    openai_api_key: SecretStr | None = None
    openai_call_model: str = "gpt-4o-mini"
    openai_reasoning_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dim: int = 3072
    embedding_provider: Literal["openai", "local"] = "local"
    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    local_embedding_dim: int = 768

    generation_provider: Literal["local", "openai","gemini"] = "local"
    local_generation_model: str = "Qwen/Qwen2.5-7B-Instruct"
    generation_device: str = "cuda"
    generation_max_new_tokens: int = 512
    generation_temperature: float = 0.2
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

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
    # Aliased to the classic LANGCHAIN_* names because that's what's in .env —
    # LangSmith/LangChain both still read these directly from os.environ at
    # call time, independent of this Settings object (see _export_to_environ below).
    langsmith_tracing: bool = Field(default=False, validation_alias="LANGCHAIN_TRACING_V2")
    langsmith_api_key: SecretStr | None = Field(default=None, validation_alias="LANGCHAIN_API_KEY")
    langsmith_project: str = Field(default="outbound-ai-arabic", validation_alias="LANGCHAIN_PROJECT")
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com", validation_alias="LANGCHAIN_ENDPOINT"
    )

    # ------------------------------------------------------------------ Telephony
    telephony_provider: Literal["simulated", "vonage"] = "simulated"
    vonage_api_key: str = ""
    vonage_api_secret: SecretStr | None = None
    vonage_application_id: str = ""
    vonage_private_key_path: Path = Path("./vonage_private.key")
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

    @property
    def vonage_private_key_full_path(self) -> Path:
        path = self.vonage_private_key_path
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    def export_tracing_env(self) -> None:
        """Push the vars LangChain/LangSmith read directly from os.environ.

        pydantic-settings' env_file only populates *this* object, it never
        touches os.environ — so libraries that read os.environ themselves
        (langsmith, langchain core tracing) stay blind to .env unless we do
        this explicitly. Call once, at process startup, before building any
        graph or making any LLM call.
        """
        os.environ["LANGCHAIN_TRACING_V2"] = "true" if self.langsmith_tracing else "false"
        os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = self.langsmith_endpoint
        if self.langsmith_api_key:
            os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. Call get_settings.cache_clear() in tests to reload."""
    settings = Settings()
    settings.export_tracing_env()
    return settings
