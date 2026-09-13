"""Environment-backed settings."""

from __future__ import annotations

from faunalab.settings import Settings


def test_default_thresholds() -> None:
    settings = Settings()
    assert settings.port == 8000
    assert settings.confidence_threshold == 0.5
    assert settings.other_mass_threshold == 0.5


def test_cors_origin_list_parses_csv() -> None:
    settings = Settings(cors_origins="http://localhost:5173, http://127.0.0.1:5173")
    assert settings.cors_origin_list() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_empty_cors_is_same_origin_only() -> None:
    settings = Settings(cors_origins="")
    assert settings.cors_origin_list() == []
