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
