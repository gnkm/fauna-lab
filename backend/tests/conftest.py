"""Shared pytest fixtures and VER-* markers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.settings import Settings, get_settings

from tests.ver_catalog import (
    load_matrix,
    marker_slug,
    ver_id_from_test_name,
    ver_ids_in_text,
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "ver(id): SRS 4 章の検証識別子（例: VER-OBS-001）",
    )
    for row in load_matrix():
        slug = marker_slug(row.ver_id)
        config.addinivalue_line("markers", f"{slug}: {row.ver_id}")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        function = getattr(item, "function", None)
        if function is None:
            continue
        found = ver_ids_in_text(function.__doc__ or "")
        from_name = ver_id_from_test_name(function.__name__)
        if from_name is not None:
            found.add(from_name)
        for ver_id in sorted(found):
            item.add_marker(pytest.mark.ver(ver_id))
            item.add_marker(getattr(pytest.mark, marker_slug(ver_id)))


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
