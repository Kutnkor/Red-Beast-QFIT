"""Central configuration. All values come from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Q-FIT"
APP_FULL_NAME = "Quantum Framework for Intelligent Tracking"
APP_VERSION = "0.1.0"
API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI. SecretStr keeps the key out of logs, reprs and error messages.
    llm_provider: Literal["gemini", "openai", "ollama"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_model: str = ""                    # required with LLM_PROVIDER=openai; pick one your account can use
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_effort: str = ""         # e.g. "none" for gpt-6-sol; empty = model default
    ai_fallback_enabled: bool = True          # answer /chat from the knowledge base when the model fails
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""                    # e.g. a tool-calling model pulled with `ollama pull`
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    ai_max_tool_steps: int = Field(6, ge=1, le=12)
    ai_timeout_seconds: float = Field(60, gt=0)
    chat_timeout_seconds: float = Field(90, gt=0)   # whole /chat turn; past it the answer falls back
    gemini_embedding_model: str = ""          # empty: lexical retrieval only
    qfit_instruction_version: str = "v2"
    rag_enabled: bool = True
    rag_top_k: int = Field(4, ge=1, le=8)
    qfit_data_dir: str = "data"               # runtime data (candidate log); relative to the backend root

    # Data sources
    spherex_base_url: str = "https://irsa.ipac.caltech.edu"
    horizons_api_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"

    # Server
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Limits
    http_timeout_seconds: float = Field(20, gt=0)   # healthy IRSA answers in 2-3 s; caps outage waits
    http_max_retries: int = Field(2, ge=0, le=5)
    cache_ttl_seconds: int = Field(600, ge=0)
    max_request_body_bytes: int = Field(65536, ge=1024)
    chat_rate_limit_per_minute: int = Field(20, ge=0)        # per client IP
    chat_daily_limit: int = Field(500, ge=0)                 # model calls per UTC day for the whole site; 0 = off
    trust_proxy_headers: bool = False                        # true behind a reverse proxy / hosting platform
    qfit_team_token: SecretStr | None = None                 # required for candidate writes when set
    max_search_radius_deg: float = Field(2.0, gt=0)
    max_archive_records: int = Field(5000, ge=1)
    max_cutout_download_bytes: int = Field(40_000_000, ge=1)

    @property
    def gemini_key(self) -> str | None:
        if self.gemini_api_key is None:
            return None
        return self.gemini_api_key.get_secret_value().strip() or None

    @property
    def openai_key(self) -> str | None:
        if self.openai_api_key is None:
            return None
        return self.openai_api_key.get_secret_value().strip() or None

    @property
    def team_token(self) -> str | None:
        if self.qfit_team_token is None:
            return None
        return self.qfit_team_token.get_secret_value().strip() or None

    @property
    def active_model(self) -> str:
        return {"ollama": self.ollama_model, "openai": self.openai_model}.get(self.llm_provider, self.gemini_model)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
