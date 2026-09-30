"""Environment-backed settings; no secrets have code defaults."""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    worker_database_url: str | None = None
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_storage_secret_key: str | None = None
    supabase_storage_bucket: str = "playeriq-reports"
    jwks_cache_seconds: int = Field(default=300, ge=30, le=600)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=25 * 1024 * 1024)
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_velocity_review_kmh: Decimal = Field(default=Decimal("45"), gt=0, le=100)
    distance_peer_review_multiplier: Decimal = Field(default=Decimal("3"), gt=1)
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-luna"
    ai_request_timeout_seconds: int = Field(default=25, ge=5, le=120)
    ai_max_tool_calls: int = Field(default=4, ge=1, le=8)
    ai_max_provider_attempts: int = Field(default=2, ge=1, le=3)
    ai_max_question_length: int = Field(default=600, ge=40, le=2000)
    ai_max_context_messages: int = Field(default=6, ge=0, le=20)
    ai_max_result_facts: int = Field(default=24, ge=1, le=60)
    ai_max_session_results: int = Field(default=10, ge=1, le=10)
    ai_max_response_length: int = Field(default=1200, ge=200, le=3000)
    ai_max_date_range_days: int = Field(default=366, ge=1, le=3660)
    ai_daily_run_limit: int = Field(default=20, ge=1, le=200)

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.rstrip("/")
        if not value.startswith("https://"):
            raise ValueError("SUPABASE_URL must use HTTPS")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
