"""Environment-backed settings; no secrets have code defaults."""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_velocity_review_kmh: Decimal = Field(default=Decimal("45"), gt=0, le=100)
    distance_peer_review_multiplier: Decimal = Field(default=Decimal("3"), gt=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
