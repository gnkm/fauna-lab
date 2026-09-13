"""Sample import (F009 / REQ-F-SYS-003).

Verification mapping:
- VER-F-SYS-001 sample portion: test_ver_f_sys_001_sample_import_registers_labels
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.settings import Settings, get_settings
from PIL import Image


def _jpeg(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (20, 16), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _write_sample(assets: Path, items: list[tuple[str, str, bytes]]) -> None:
    sample = assets / "sample"
    (sample / "images").mkdir(parents=True)
    manifest_items = []
    for filename, class_id, data in items:
        relative = f"images/{filename}"
        (sample / relative).write_bytes(data)
        manifest_items.append({"file": relative, "class_id": class_id})
    (sample / "manifest.json").write_text(
        json.dumps({"manifest_version": 1, "items": manifest_items}),
        encoding="utf-8",
    )


def test_ver_f_sys_001_sample_import_registers_labels(settings: Settings) -> None:
    """VER-F-SYS-001: サンプル投入で画像と確定ラベルが載る。"""
    _write_sample(
        settings.assets_dir,
        [
            ("samoyed_1.jpg", "samoyed", _jpeg((200, 200, 200))),
            ("boxer_1.jpg", "boxer", _jpeg((10, 10, 10))),
        ],
    )
    with TestClient(create_app(settings)) as client:
        empty = client.get("/api/_state").json()
        assert empty["images"] == []
        imported = client.post("/api/sample/import")
        assert imported.status_code == 200
        assert imported.json() == {"updated_count": 2}
        images = client.get("/api/_state").json()["images"]
        assert len(images) == 2
        labels = {item["label"]["class_id"] for item in images}
        assert labels == {"samoyed", "boxer"}
        assert all(item["label"]["source"] == "human" for item in images)
        assert all(item["suggestion"] is None for item in images)


def test_sample_import_is_idempotent(settings: Settings) -> None:
    _write_sample(
        settings.assets_dir,
        [("a.jpg", "chihuahua", _jpeg((1, 2, 3)))],
    )
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/sample/import")
        second = client.post("/api/sample/import")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json() == {"updated_count": 1}
        assert len(client.get("/api/_state").json()["images"]) == 1


def test_invalid_later_sample_does_not_persist_earlier_items(
    settings: Settings,
) -> None:
    """後半が壊れていても、事前検証で前半を書き込まない。"""
    _write_sample(
        settings.assets_dir,
        [
            ("ok.jpg", "samoyed", _jpeg((200, 0, 0))),
            ("bad.jpg", "boxer", b"not-an-image"),
        ],
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/sample/import")
        assert response.status_code == 422
        assert response.json()["code"] == "sample_unavailable"
        assert client.get("/api/_state").json()["images"] == []


def test_missing_sample_is_422_and_startup_continues(tmp_path: Path) -> None:
    """REQ-F-SYS-003: sample 欠落は明確な誤り。起動は継続する。"""
    get_settings.cache_clear()
    settings = Settings(
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "missing-assets",
        web_dist_dir=tmp_path / "missing-dist",
    )
    with TestClient(create_app(settings)) as client:
        state = client.get("/api/_state")
        assert state.status_code == 200
        response = client.post("/api/sample/import")
        assert response.status_code == 422
        assert response.headers["content-type"].startswith(PROBLEM_JSON)
        assert response.json()["code"] == "sample_unavailable"
        assert client.get("/api/_state").status_code == 200
    get_settings.cache_clear()
