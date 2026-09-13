"""Dataset stats (F009 / REQ-F-DS-005)."""

from __future__ import annotations

import io
import sqlite3

from fastapi.testclient import TestClient
from faunalab.domain.classes import CLASS_IDS
from faunalab.persist.store import DB_FILENAME
from faunalab.settings import Settings
from PIL import Image


def _jpeg(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (12, 12), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _upload(client: TestClient, data: bytes, name: str) -> str:
    response = client.post(
        "/api/images", files=[("files", (name, data, "image/jpeg"))]
    )
    assert response.status_code == 200
    return str(response.json()["items"][0]["ref"])


def test_stats_exclude_suggestions_from_labeled(
    client: TestClient, settings: Settings
) -> None:
    labeled = _upload(client, _jpeg((255, 0, 0)), "l.jpg")
    _upload(client, _jpeg((0, 255, 0)), "u.jpg")
    suggested = _upload(client, _jpeg((0, 0, 255)), "s.jpg")
    client.put(f"/api/images/{labeled}/label", json={"class_id": "samoyed"})
    _plant_suggestion(settings, suggested, "boxer")

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["image_count"] == 3
    assert body["labeled_count"] == 1
    assert body["unlabeled_count"] == 2
    assert body["suggestion_count"] == 1
    assert body["per_class"]["samoyed"] == 1
    assert body["per_class"]["boxer"] == 0
    assert set(body["per_class"]) == set(CLASS_IDS)
    assert body["per_split"]["unassigned"] == 3
    assert body["active_model_ref"] is None
    assert body["has_active_job"] is False


def _plant_suggestion(settings: Settings, image_ref: str, class_id: str) -> None:
    conn = sqlite3.connect(settings.data_dir / DB_FILENAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        image = conn.execute(
            "SELECT id FROM images WHERE ref = ?", (image_ref,)
        ).fetchone()
        assert image is not None
        conn.execute(
            """
            INSERT INTO models (ref, version, builtin, active, created_at)
            VALUES (?, 1, 0, 0, '2024-01-01T00:00:00Z')
            """,
            ("22222222-2222-4222-8222-222222222222",),
        )
        model_row = conn.execute(
            "SELECT id FROM models WHERE version = 1"
        ).fetchone()
        model_id = int(model_row["id"])
        conn.execute(
            """
            INSERT INTO suggestions (
                image_id, class_id, confidence, model_id, created_at
            )
            VALUES (?, ?, 0.4, ?, '2024-01-01T00:00:00Z')
            """,
            (int(image["id"]), class_id, model_id),
        )
        conn.commit()
    finally:
        conn.close()
