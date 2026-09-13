"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.settings import Settings, get_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    get_settings.cache_clear()
    return Settings(
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "assets",
        web_dist_dir=tmp_path / "missing-dist",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    get_settings.cache_clear()
