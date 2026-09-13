"""Annotation API (F009).

Verification mapping:
- VER-F-ANN-001 (REQ-F-ANN-001〜007):
  test_ver_f_ann_001_overwrite_and_bulk_missing_is_atomic
"""

from __future__ import annotations

import io
import sqlite3
from typing import Any

from fastapi.testclient import TestClient
from faunalab.api.errors import PROBLEM_JSON
from faunalab.persist.store import DB_FILENAME
from faunalab.settings import Settings
from PIL import Image


def _jpeg(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    image = Image.new("RGB", (16, 16), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _upload(client: TestClient, data: bytes, name: str = "a.jpg") -> str:
    response = client.post(
        "/api/images", files=[("files", (name, data, "image/jpeg"))]
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["ok"] is True
    return str(item["ref"])


def _state(client: TestClient) -> dict[str, Any]:
    body = client.get("/api/_state").json()
    body.pop("observed_at", None)
    return body


def test_ver_f_ann_001_overwrite_and_bulk_missing_is_atomic(
    client: TestClient,
) -> None:
    """VER-F-ANN-001: 2 回付与は 1 件。一括の不在混入では `_state` が変わらない。"""
    first = _upload(client, _jpeg((1, 0, 0)), "one.jpg")
    second = _upload(client, _jpeg((0, 1, 0)), "two.jpg")

    put1 = client.put(f"/api/images/{first}/label", json={"class_id": "samoyed"})
    assert put1.status_code == 200
    assert put1.json() == {"class_id": "samoyed", "source": "human"}
    put2 = client.put(
        f"/api/images/{first}/label",
        json={"class_id": "boxer", "source": "human"},
    )
    assert put2.status_code == 200
    images = client.get("/api/_state").json()["images"]
    by_ref = {item["ref"]: item for item in images}
    assert by_ref[first]["label"] == {"class_id": "boxer", "source": "human"}
    assert by_ref[second]["label"] is None

    before = _state(client)
    missing = "00000000-0000-4000-8000-000000000099"
    failed = client.post(
        "/api/labels/bulk",
        json={"refs": [first, missing], "class_id": "chihuahua"},
    )
    assert failed.status_code == 404
    assert failed.headers["content-type"].startswith(PROBLEM_JSON)
    assert failed.json()["code"] == "image_not_found"
    assert _state(client) == before
    assert by_ref[first]["label"]["class_id"] == "boxer"


def test_label_timestamp_is_updated_on_overwrite(
    client: TestClient, settings: Settings, monkeypatch: Any
) -> None:
    """REQ-F-ANN-003: 上書きで付与時刻が更新される。"""
    times = iter(["2024-01-01T00:00:00Z", "2024-01-01T00:00:05Z"])
    monkeypatch.setattr("faunalab.api.labels.utc_now_z", lambda: next(times))
    ref = _upload(client, _jpeg((3, 3, 3)))
    client.put(f"/api/images/{ref}/label", json={"class_id": "havanese"})
    first_at = _label_created_at(settings, ref)
    client.put(f"/api/images/{ref}/label", json={"class_id": "pomeranian"})
    second_at = _label_created_at(settings, ref)
    assert first_at == "2024-01-01T00:00:00Z"
    assert second_at == "2024-01-01T00:00:05Z"


def test_label_clears_suggestion(client: TestClient, settings: Settings) -> None:
    """REQ-F-ANN-007: 確定付与で候補が消える。"""
    ref = _upload(client, _jpeg((9, 9, 9)))
    _plant_suggestion(settings, ref, "boxer")
    before = client.get("/api/_state").json()["images"][0]
    assert before["suggestion"] is not None
    assert before["label"] is None
    client.put(
        f"/api/images/{ref}/label",
        json={"class_id": "samoyed", "source": "model_suggested"},
    )
    after = client.get("/api/_state").json()["images"][0]
    assert after["label"] == {"class_id": "samoyed", "source": "model_suggested"}
    assert after["suggestion"] is None


def test_bulk_success_returns_updated_count(client: TestClient) -> None:
    """REQ-F-ANN-004 / 005: 全件存在すれば同一クラスを付与し件数を返す。"""
    refs = [
        _upload(client, _jpeg((i, 0, 0)), f"{i}.jpg") for i in range(1, 4)
    ]
    response = client.post(
        "/api/labels/bulk",
        json={"refs": refs, "class_id": "chihuahua"},
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 3}
    labels = {
        item["ref"]: item["label"]
        for item in client.get("/api/_state").json()["images"]
    }
    for ref in refs:
        assert labels[ref] == {"class_id": "chihuahua", "source": "human"}


def test_bulk_lookup_chunks_refs(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr("faunalab.persist.store.IN_QUERY_CHUNK", 1)
    refs = [
        _upload(client, _jpeg((255, index, 0)), f"{index}.jpg")
        for index in (10, 40, 80)
    ]
    response = client.post(
        "/api/labels/bulk",
        json={"refs": refs, "class_id": "boxer"},
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 3}


def test_delete_label_resets_split(client: TestClient) -> None:
    ref = _upload(client, _jpeg((4, 5, 6)))
    client.put(f"/api/images/{ref}/label", json={"class_id": "boxer"})
    split = client.post("/api/splits", json={})
    assert split.status_code == 200
    assert client.get("/api/_state").json()["images"][0]["split"] in {
        "train",
        "val",
        "test",
    }
    deleted = client.delete(f"/api/images/{ref}/label")
    assert deleted.status_code == 204
    image = client.get("/api/_state").json()["images"][0]
    assert image["label"] is None
    assert image["split"] == "unassigned"


def test_put_label_unknown_image_is_404(client: TestClient) -> None:
    response = client.put(
        "/api/images/00000000-0000-4000-8000-000000000001/label",
        json={"class_id": "samoyed"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "image_not_found"


def _label_created_at(settings: Settings, ref: str) -> str:
    conn = sqlite3.connect(settings.data_dir / DB_FILENAME)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT l.created_at AS created_at
            FROM labels AS l
            JOIN images AS i ON i.id = l.image_id
            WHERE i.ref = ?
            """,
            (ref,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return str(row["created_at"])


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
            ("11111111-1111-4111-8111-111111111111",),
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
            VALUES (?, ?, 0.9, ?, '2024-01-01T00:00:00Z')
            """,
            (int(image["id"]), class_id, model_id),
        )
        conn.commit()
    finally:
        conn.close()
