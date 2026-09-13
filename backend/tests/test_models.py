"""Model management API (F013 / REQ-F-MDL-001〜009).

Verification mapping:
- VER-DATA-004: test_ver_data_004_baseline_reeval_matches_annex
- VER-F-MDL-001: test_metrics.test_ver_f_mdl_001_matrix_identity
  and the re-eval test's matrix checks
- VER-F-MDL-002 (学習不要分):
  test_ver_f_mdl_002_version_zero_active_delete_refused_restart
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.classes import CLASS_IDS
from faunalab.domain.models import register_trained_model
from faunalab.persist.store import DB_FILENAME, Store
from faunalab.settings import Settings, get_settings

REPO_ASSETS = Path(__file__).resolve().parents[2] / "assets"
FIXTURES = REPO_ASSETS / "fixtures"
METRICS_TOLERANCE = 0.0001
ANNEX_EXPECTED: dict[str, Any] = {
    "accuracy": 0.7778,
    "per_class": {
        "samoyed": {
            "precision": 0.8889,
            "recall": 1.0,
            "f1": 0.9412,
            "support": 8,
        },
        "great_pyrenees": {
            "precision": 1.0,
            "recall": 0.8571,
            "f1": 0.9231,
            "support": 7,
        },
        "boxer": {
            "precision": 0.5455,
            "recall": 1.0,
            "f1": 0.7059,
            "support": 6,
        },
        "american_bulldog": {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "support": 5,
        },
        "chihuahua": {
            "precision": 0.8,
            "recall": 1.0,
            "f1": 0.8889,
            "support": 4,
        },
        "miniature_pinscher": {
            "precision": 1.0,
            "recall": 0.6667,
            "f1": 0.8,
            "support": 3,
        },
        "pomeranian": {
            "precision": 0.6667,
            "recall": 1.0,
            "f1": 0.8,
            "support": 2,
        },
        "havanese": {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "support": 1,
        },
    },
    "confusion_matrix": {
        "labels": list(CLASS_IDS),
        "matrix": [
            [8, 0, 0, 0, 0, 0, 0, 0],
            [1, 6, 0, 0, 0, 0, 0, 0],
            [0, 0, 6, 0, 0, 0, 0, 0],
            [0, 0, 5, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 4, 0, 0, 0],
            [0, 0, 0, 0, 1, 2, 0, 0],
            [0, 0, 0, 0, 0, 0, 2, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
        ],
    },
}


def assert_metrics_close(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    tolerance: float = METRICS_TOLERANCE,
) -> None:
    assert abs(float(actual["accuracy"]) - float(expected["accuracy"])) <= tolerance
    actual_per = actual["per_class"]
    expected_per = expected["per_class"]
    assert set(actual_per) == set(CLASS_IDS)
    assert list(actual["confusion_matrix"]["labels"]) == list(CLASS_IDS)
    for class_id in CLASS_IDS:
        got = actual_per[class_id]
        exp = expected_per[class_id]
        assert got["support"] == exp["support"]
        for key in ("precision", "recall", "f1"):
            assert abs(float(got[key]) - float(exp[key])) <= tolerance, class_id
    assert (
        actual["confusion_matrix"]["matrix"] == expected["confusion_matrix"]["matrix"]
    )


def _settings(tmp_path: Path, assets_dir: Path) -> Settings:
    get_settings.cache_clear()
    return Settings(
        data_dir=tmp_path / "data",
        assets_dir=assets_dir,
        web_dist_dir=tmp_path / "missing-dist",
    )


@pytest.fixture
def assets_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _settings(tmp_path, REPO_ASSETS)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    get_settings.cache_clear()


def _app_store(client: TestClient) -> Store:
    app = client.app
    assert isinstance(app, FastAPI)
    store = app.state.store
    assert isinstance(store, Store)
    return store


def _state(client: TestClient) -> dict[str, Any]:
    return client.get("/api/_state").json()


def _version_zero(client: TestClient) -> dict[str, Any]:
    models = _state(client)["models"]
    assert models
    zero = models[0]
    assert zero["version"] == 0
    return zero


def test_list_and_get_version_zero(assets_client: TestClient) -> None:
    listed = assets_client.get("/api/models")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["version"] == 0
    assert item["builtin"] is True
    assert item["active"] is True
    assert item["metrics"] is None
    got = assets_client.get(f"/api/models/{item['ref']}")
    assert got.status_code == 200
    assert got.json()["ref"] == item["ref"]


def test_unknown_model_is_404(assets_client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000099"
    response = assets_client.get(f"/api/models/{missing}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["code"] == "model_not_found"


def test_delete_version_zero_fails(assets_client: TestClient) -> None:
    ref = _version_zero(assets_client)["ref"]
    response = assets_client.delete(f"/api/models/{ref}")
    assert response.status_code == 409
    assert response.json()["code"] == "model_not_deletable"
    assert _state(assets_client)["models"][0]["version"] == 0


def test_evaluate_empty_test_split_fails(assets_client: TestClient) -> None:
    ref = _version_zero(assets_client)["ref"]
    response = assets_client.post(f"/api/models/{ref}/evaluate")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["code"] == "empty_test_split"
    assert _state(assets_client)["models"][0]["metrics"] is None


def test_ver_f_mdl_002_version_zero_active_delete_refused_restart(
    tmp_path: Path,
) -> None:
    """初期状態で版 0 が有効、削除拒否、再起動後も active。"""

    settings = _settings(tmp_path, REPO_ASSETS)
    with TestClient(create_app(settings)) as client:
        models = _state(client)["models"]
        assert len(models) == 1
        assert models[0]["version"] == 0
        assert models[0]["active"] is True
        refused = client.delete(f"/api/models/{models[0]['ref']}")
        assert refused.status_code == 409
        assert refused.json()["code"] == "model_not_deletable"
        first_ref = models[0]["ref"]
    with TestClient(create_app(settings)) as client:
        models = _state(client)["models"]
        assert models[0]["ref"] == first_ref
        assert models[0]["active"] is True
        listed = client.get("/api/models").json()["items"]
        assert listed[0]["active"] is True


def test_first_trained_model_auto_activates(assets_client: TestClient) -> None:
    """REQ-F-MDL-004 の契約。F014 は register_trained_model を使う。"""

    store = _app_store(assets_client)
    created_at = "2026-09-13T00:00:00Z"
    first = register_trained_model(store, ref=str(uuid.uuid4()), created_at=created_at)
    assert first.version == 1
    assert first.active is True
    assert first.builtin is False
    assert first.metrics is None
    models = {item["version"]: item for item in _state(assets_client)["models"]}
    assert models[0]["active"] is False
    assert models[1]["active"] is True
    second = register_trained_model(store, ref=str(uuid.uuid4()), created_at=created_at)
    assert second.version == 2
    assert second.active is False
    models = {item["version"]: item for item in _state(assets_client)["models"]}
    assert models[1]["active"] is True
    assert models[2]["active"] is False
    listed = assets_client.get("/api/models").json()["items"]
    assert [item["version"] for item in listed] == [2, 1, 0]


def test_activate_keeps_at_most_one_active(assets_client: TestClient) -> None:
    store = _app_store(assets_client)
    v0 = _version_zero(assets_client)["ref"]
    first = register_trained_model(
        store, ref=str(uuid.uuid4()), created_at="2026-09-13T00:00:00Z"
    )
    activated = assets_client.post(f"/api/models/{v0}/activate")
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    models = _state(assets_client)["models"]
    actives = [item for item in models if item["active"]]
    assert len(actives) == 1
    assert actives[0]["ref"] == v0
    assert assets_client.get(f"/api/models/{first.ref}").json()["active"] is False


def test_delete_active_trained_model_fails(assets_client: TestClient) -> None:
    store = _app_store(assets_client)
    trained = register_trained_model(
        store, ref=str(uuid.uuid4()), created_at="2026-09-13T00:00:00Z"
    )
    response = assets_client.delete(f"/api/models/{trained.ref}")
    assert response.status_code == 409
    assert response.json()["code"] == "model_not_deletable"


def test_delete_removes_artifacts_keeps_inferences_and_does_not_reuse_version(
    assets_client: TestClient,
) -> None:
    store = _app_store(assets_client)
    v0 = _version_zero(assets_client)["ref"]
    trained = register_trained_model(
        store, ref=str(uuid.uuid4()), created_at="2026-09-13T00:00:00Z"
    )
    artifact = store.data_dir / "models" / "1"
    marker = artifact / "model.onnx"
    marker.write_bytes(b"dummy-onnx")
    assert marker.is_file()
    upload = assets_client.post(
        "/api/images",
        files=[("files", ("a.jpg", _tiny_jpeg(), "image/jpeg"))],
    )
    image_ref = upload.json()["items"][0]["ref"]
    conn = sqlite3.connect(store.data_dir / DB_FILENAME)
    conn.execute("PRAGMA foreign_keys = ON")
    image_id = conn.execute(
        "SELECT id FROM images WHERE ref = ?", (image_ref,)
    ).fetchone()[0]
    model_id = conn.execute("SELECT id FROM models WHERE version = 1").fetchone()[0]
    conn.execute(
        """
        INSERT INTO inferences (
            ref, image_id, model_id, top_class_id, top_confidence,
            other_mass, low_confidence, scores_json, created_at
        )
        VALUES (?, ?, ?, 'samoyed', 0.9, NULL, 0, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            image_id,
            model_id,
            json.dumps({class_id: 0.125 for class_id in CLASS_IDS}),
            "2026-09-13T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    assert assets_client.post(f"/api/models/{v0}/activate").status_code == 200
    deleted = assets_client.delete(f"/api/models/{trained.ref}")
    assert deleted.status_code == 204
    assert not artifact.exists()
    assert assets_client.get(f"/api/models/{trained.ref}").status_code == 404
    models = _state(assets_client)["models"]
    assert [item["version"] for item in models] == [0]
    inferences = _state(assets_client)["inferences"]
    assert len(inferences) == 1
    assert inferences[0]["model_ref"] == trained.ref

    reused = register_trained_model(
        store, ref=str(uuid.uuid4()), created_at="2026-09-13T00:00:01Z"
    )
    assert reused.version == 2


def test_ver_data_004_baseline_reeval_matches_annex(
    assets_client: TestClient,
) -> None:
    """附属書 5.3 の 36 枚を試験分割へ載せ、版 0 を再評価する。"""

    payload = json.loads(
        (FIXTURES / "metrics_fixture.json").read_text(encoding="utf-8")
    )
    items = payload["items"]
    files = []
    for item in items:
        path = FIXTURES / item["file"]
        files.append(("files", (item["file"], path.read_bytes(), "image/jpeg")))
    uploaded = assets_client.post("/api/images", files=files)
    assert uploaded.status_code == 200
    by_name = {
        entry["filename"]: entry["ref"]
        for entry in uploaded.json()["items"]
        if entry["ok"]
    }
    assert len(by_name) == 36
    grouped: dict[str, list[str]] = {}
    for item in items:
        grouped.setdefault(item["assigned_class_id"], []).append(by_name[item["file"]])
    for class_id, refs in grouped.items():
        labeled = assets_client.post(
            "/api/labels/bulk",
            json={"refs": refs, "class_id": class_id},
        )
        assert labeled.status_code == 200
    assignments = {ref: "test" for ref in by_name.values()}
    _app_store(assets_client).apply_split_assignments(assignments)

    zero = _version_zero(assets_client)
    evaluated = assets_client.post(f"/api/models/{zero['ref']}/evaluate")
    assert evaluated.status_code == 200
    metrics = evaluated.json()["metrics"]
    assert_metrics_close(metrics, ANNEX_EXPECTED)
    observed = _state(assets_client)
    state_metrics = next(
        item["metrics"] for item in observed["models"] if item["version"] == 0
    )
    assert_metrics_close(state_metrics, ANNEX_EXPECTED)
    matrix = state_metrics["confusion_matrix"]["matrix"]
    total = sum(sum(row) for row in matrix)
    assert total == 36
    diagonal = sum(matrix[i][i] for i in range(8))
    assert abs(diagonal / total - state_metrics["accuracy"]) <= 0.001
    assert state_metrics["confusion_matrix"]["labels"] == [
        item["class_id"] for item in observed["classes"]
    ]

    refused = assets_client.delete(f"/api/models/{zero['ref']}")
    assert refused.status_code == 409


def _tiny_jpeg() -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (16, 16), (1, 2, 3))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()
