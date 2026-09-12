"""Environment-backed settings (ARCHITECTURE.md 6.1)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_web_dist_dir() -> Path:
    container = Path("/app/web/dist")
    if container.is_dir():
        return container
    return Path(__file__).resolve().parents[2] / "web" / "dist"


class Settings(BaseSettings):
    """Runtime configuration from `FAUNALAB_*` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="FAUNALAB_",
        env_parse_none_str="",
        extra="ignore",
    )

    port: int = 8000
    data_dir: Path = Path("/var/lib/faunalab")
    assets_dir: Path = Path("/var/lib/faunalab-assets")
    cors_origins: str = ""
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    other_mass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    web_dist_dir: Path = Field(default_factory=_default_web_dist_dir)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _normalize_cors(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
