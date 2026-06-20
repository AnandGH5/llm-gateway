from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """12-factor configuration. Every knob is env-driven (see .env.example).

    Field names map case-insensitively to env vars, e.g. ``primary_provider``
    is read from ``PRIMARY_PROVIDER``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- providers ---
    primary_provider: str = "mock"
    fallback_provider: str | None = None  # used from Phase 4 (failover)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    provider_timeout_seconds: float = 30.0
    max_retries: int = 2

    # --- gateway auth ---
    # Comma-separated list of accepted gateway keys (sent as `Bearer <key>`).
    gateway_api_keys: str = "gw_sk_demo123"

    # --- server ---
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def allowed_keys(self) -> set[str]:
        return {k.strip() for k in self.gateway_api_keys.split(",") if k.strip()}


settings = Settings()
