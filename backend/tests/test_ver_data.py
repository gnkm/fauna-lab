"""VER-DATA-002 / VER-DATA-003: 不変条件と生成ファイルの範囲。"""

from __future__ import annotations

import io
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.domain.models import register_trained_model
from faunalab.persist.store import DB_FILENAME, Store
from faunalab.settings import Settings, get_settings
from PIL import Image

from tests.invariants import (
    assert_job_kept_after_model_delete,
    assert_observation_invariants,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_ASSETS = REPO_ROOT / "assets"


def _jpeg(color: tuple[int, int, int], salt: int = 0) -> bytes:
    image = Image.new("RGB", (24, 16), color)
    image.putpixel((salt % 24, 0), ((color[0] + salt) % 256, 1, 2))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _upload(client: TestClient, data: bytes, name: str) -> str:
    response = client.post(
        "/api/images", files=[("files", (name, data, "image/jpeg"))]
    )
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["ok"] is True
    return str(item["ref"])


def _state(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/_state")
    assert response.status_code == 200
    return response.json()


def _client_store(client: TestClient) -> Store:
    app = client.app
    assert isinstance(app, FastAPI)
    store = app.state.store
    assert isinstance(store, Store)
    return store


def _insert_succeeded_job(db_path: Path, *, job_ref: str, model_ref: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        model_id = conn.execute(
            "SELECT id FROM models WHERE ref = ?", (model_ref,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO jobs (
                ref, status, current_epoch, total_epochs, model_id,
                created_at
            )
            VALUES (?, 'SUCCEEDED', 1, 1, ?, ?)
            """,
            (job_ref, model_id, "2026-09-13T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def test_ver_data_002_invariants_hold_after_operations(tmp_path: Path) -> None:
    """VER-DATA-002: 不変条件を破ろうとする操作の直後も `_state` が健全。"""

    settings = Settings(
        data_dir=tmp_path / "data",
        assets_dir=REPO_ASSETS,
        web_dist_dir=tmp_path / "missing-dist",
    )
    get_settings.cache_clear()
    with TestClient(create_app(settings)) as client:
        first = _upload(client, _jpeg((10, 0, 0), 1), "one.jpg")
        assert_observation_invariants(_state(client))

        second = _upload(client, _jpeg((0, 10, 0), 2), "two.jpg")
        labeled = client.put(
            f"/api/images/{first}/label",
            json={"class_id": "samoyed", "source": "human"},
        )
        assert labeled.status_code == 200
        assert_observation_invariants(_state(client))

        again = client.put(
            f"/api/images/{first}/label",
            json={"class_id": "boxer", "source": "human"},
        )
        assert again.status_code == 200
        state = _state(client)
        by_ref = {item["ref"]: item for item in state["images"]}
        assert by_ref[first]["label"] == {"class_id": "boxer", "source": "human"}
        assert by_ref[second]["label"] is None
        assert_observation_invariants(state)

        duplicate = client.post(
            "/api/images",
            files=[("files", ("dup.jpg", _jpeg((10, 0, 0), 1), "image/jpeg"))],
        )
        assert duplicate.status_code == 409
        assert_observation_invariants(_state(client))

        missing = "00000000-0000-4000-8000-000000000099"
        bulk = client.post(
            "/api/labels/bulk",
            json={"refs": [first, missing], "class_id": "chihuahua"},
        )
        assert bulk.status_code == 404
        assert_observation_invariants(_state(client))

        deleted = client.delete(f"/api/images/{first}")
        assert deleted.status_code == 204
        after = _state(client)
        assert all(item["ref"] != first for item in after["images"])
        assert_observation_invariants(after)

        store = _client_store(client)
        trained = register_trained_model(
            store,
            ref=str(uuid.uuid4()),
            created_at="2026-09-13T00:00:00Z",
        )
        job_ref = str(uuid.uuid4())
        _insert_succeeded_job(
            settings.data_dir / DB_FILENAME,
            job_ref=job_ref,
            model_ref=trained.ref,
        )
        assert_observation_invariants(_state(client))

        v0 = next(item for item in _state(client)["models"] if item["version"] == 0)
        activated = client.post(f"/api/models/{v0['ref']}/activate")
        assert activated.status_code == 200
        assert_observation_invariants(_state(client))

        removed = client.delete(f"/api/models/{trained.ref}")
        assert removed.status_code == 204
        final = _state(client)
        assert_job_kept_after_model_delete(
            final, job_ref=job_ref, deleted_model_ref=trained.ref
        )
        assert_observation_invariants(final)
    get_settings.cache_clear()


def test_ver_data_003_writes_stay_in_data_dir(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    """VER-DATA-003: 一連の操作後、規定範囲外に新規ファイルが無い。"""

    watched = [
        REPO_ROOT / DB_FILENAME,
        REPO_ROOT / "data" / DB_FILENAME,
        Path.cwd() / DB_FILENAME,
    ]
    existed = {path: path.exists() for path in watched}
    before = {p.resolve() for p in tmp_path.rglob("*") if p.is_file()}

    ref = _upload(client, _jpeg((3, 4, 5), 9), "../../../etc/passwd.jpg")
    client.put(
        f"/api/images/{ref}/label",
        json={"class_id": "samoyed", "source": "human"},
    )
    client.delete(f"/api/images/{ref}")
    _upload(client, _jpeg((6, 7, 8), 11), "ok.jpg")

    after = {p.resolve() for p in tmp_path.rglob("*") if p.is_file()}
    created = after - before
    assert created
    for path in created:
        assert path.is_relative_to(settings.data_dir.resolve())
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path.parent / "etc" / "passwd.jpg").exists()
    target = (settings.data_dir / DB_FILENAME).resolve()
    for path in watched:
        if path.resolve() == target:
            continue
        assert path.exists() == existed[path], f"unexpected write at {path}"
