"""Label suggestion API (F012).

Verification mapping:
- VER-F-SUG-001: test_ver_f_sug_001_generate_skips_labeled_and_needs_model
- VER-F-SUG-002: test_ver_f_sug_002_label_clears_and_regenerate_overwrites
- VER-F-SUG-003: test_ver_f_sug_003_threshold_accept_sets_model_suggested
- VER-F-SUG-004: test_ver_f_sug_004_suggestions_are_not_confirmed_labels
"""

from __future__ import annotations

import io
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.classes import CLASS_IDS
from faunalab.domain.models import register_trained_model
from faunalab.domain.suggestions import MAX_SUGGESTION_IMAGES
from faunalab.ml.fold import FoldResult
from faunalab.ml.predict import load_onnx_session
from faunalab.ml.train import (
    EMBEDDING_DIM,
    N_CLASSES,
    export_cnn_onnx,
    export_linear_onnx,
)
from faunalab.persist.store import Store, SuggestionNew
from faunalab.settings import Settings, get_settings
from PIL import Image

REPO_ASSETS = Path(__file__).resolve().parents[2] / "assets"


def _settings(tmp_path: Path, assets_dir: Path) -> Settings:
    get_settings.cache_clear()
    return Settings(
        data_dir=tmp_path / "data",
        assets_dir=assets_dir,
        web_dist_dir=tmp_path / "missing-dist",
    )


def _copy_baseline(tmp_path: Path) -> Path:
    dest = tmp_path / "assets"
    shutil.copytree(REPO_ASSETS / "baseline", dest / "baseline")
    return dest


@pytest.fixture
def baseline_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _settings(tmp_path, _copy_baseline(tmp_path))
    with TestClient(create_app(settings)) as client:
        yield client
    get_settings.cache_clear()


def _unique_png(index: int) -> bytes:
    image = Image.new("RGB", (8, 8), (index % 256, (index // 256) % 256, 40))
    image.putpixel((0, 0), (index % 256, (index // 256) % 256, (index // 65536) % 256))
    image.putpixel((7, 7), ((index * 13) % 256, (index * 17) % 256, (index * 19) % 256))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_many(client: TestClient, parts: list[tuple[str, bytes]]) -> list[str]:
    files = [("files", (name, data, "image/png")) for name, data in parts]
    response = client.post("/api/images", files=files)
    assert response.status_code == 200, response.text
    refs: list[str] = []
    for item in response.json()["items"]:
        assert item["ok"] is True, item
        refs.append(str(item["ref"]))
    return refs


def _upload_n(client: TestClient, count: int, start: int = 0) -> list[str]:
    refs: list[str] = []
    remaining = count
    index = start
    while remaining:
        chunk = min(remaining, 50)
        parts = [
            (f"{index + offset}.png", _unique_png(index + offset))
            for offset in range(chunk)
        ]
        refs.extend(_upload_many(client, parts))
        remaining -= chunk
        index += chunk
    return refs


def _client_store(client: TestClient) -> Store:
    app = client.app
    assert isinstance(app, FastAPI)
    store = app.state.store
    assert isinstance(store, Store)
    return store


def _fold(class_id: str, confidence: float) -> FoldResult:
    rest = (1.0 - confidence) / (len(CLASS_IDS) - 1)
    scores = {item: rest for item in CLASS_IDS}
    scores[class_id] = confidence
    return FoldResult(
        scores=scores,
        other_mass=0.0,
        uniform_fallback=False,
        top_class_id=class_id,
        top_confidence=confidence,
    )


def _patch_infer(client: TestClient, results: list[FoldResult]) -> Any:
    app = client.app
    assert isinstance(app, FastAPI)
    runtime = app.state.baseline_runtime
    assert runtime is not None
    return patch.object(
        runtime,
        "infer_images",
        side_effect=lambda images: results[: len(images)],
    )


def test_ver_f_sug_001_generate_skips_labeled_and_needs_model(
    baseline_client: TestClient, tmp_path: Path
) -> None:
    """VER-F-SUG-001: 未ラベル 10 + 確定 3。読み飛ばし件数。モデル無しは失敗。"""
    unlabeled = _upload_n(baseline_client, 10)
    labeled = _upload_n(baseline_client, 3, start=10)
    for ref in labeled:
        put = baseline_client.put(
            f"/api/images/{ref}/label", json={"class_id": "samoyed"}
        )
        assert put.status_code == 200

    results = [_fold("boxer", 0.81) for _ in range(10)]
    with _patch_infer(baseline_client, results):
        generated = baseline_client.post(
            "/api/suggestions", json={"refs": unlabeled + labeled}
        )
    assert generated.status_code == 200, generated.text
    assert generated.json() == {
        "generated_count": 10,
        "skipped_labeled_count": 3,
    }

    by_ref = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    for ref in unlabeled:
        suggestion = by_ref[ref]["suggestion"]
        assert suggestion is not None
        assert suggestion["class_id"] == "boxer"
        assert suggestion["confidence"] == pytest.approx(0.81)
        assert suggestion["model_ref"]
    for ref in labeled:
        assert by_ref[ref]["suggestion"] is None
        assert by_ref[ref]["label"] == {"class_id": "samoyed", "source": "human"}

    empty = _settings(tmp_path / "no-model", tmp_path / "no-model-assets")
    with TestClient(create_app(empty)) as no_model:
        failed = no_model.post("/api/suggestions", json={"refs": unlabeled[:1]})
        assert failed.status_code == 422
        assert failed.headers["content-type"].startswith(PROBLEM_JSON)
        assert failed.json()["code"] == "no_active_model"
    get_settings.cache_clear()


def test_ver_f_sug_002_label_clears_and_regenerate_overwrites(
    baseline_client: TestClient,
) -> None:
    """VER-F-SUG-002: 確定付与で候補が消え、再生成は 1 件のまま上書きする。"""
    ref = _upload_n(baseline_client, 1)[0]
    with _patch_infer(baseline_client, [_fold("boxer", 0.4)]):
        first = baseline_client.post("/api/suggestions", json={"refs": [ref]})
    assert first.status_code == 200
    assert first.json()["generated_count"] == 1
    before = baseline_client.get("/api/_state").json()["images"][0]
    assert before["suggestion"]["class_id"] == "boxer"

    labeled = baseline_client.put(
        f"/api/images/{ref}/label", json={"class_id": "havanese"}
    )
    assert labeled.status_code == 200
    cleared = baseline_client.get("/api/_state").json()["images"][0]
    assert cleared["label"] == {"class_id": "havanese", "source": "human"}
    assert cleared["suggestion"] is None

    baseline_client.delete(f"/api/images/{ref}/label")
    with _patch_infer(baseline_client, [_fold("chihuahua", 0.55)]):
        again = baseline_client.post("/api/suggestions", json={"refs": [ref]})
    assert again.status_code == 200
    with _patch_infer(baseline_client, [_fold("pomeranian", 0.77)]):
        twice = baseline_client.post("/api/suggestions", json={"refs": [ref]})
    assert twice.status_code == 200
    images = baseline_client.get("/api/_state").json()["images"]
    assert len(images) == 1
    suggestion = images[0]["suggestion"]
    assert suggestion is not None
    assert suggestion["class_id"] == "pomeranian"
    assert suggestion["confidence"] == pytest.approx(0.77)
    listed = baseline_client.get("/api/suggestions")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_ver_f_sug_003_threshold_accept_sets_model_suggested(
    baseline_client: TestClient,
) -> None:
    """VER-F-SUG-003: 閾値以上だけ採用。採用は model_suggested、人手は human。"""
    refs = _upload_n(baseline_client, 4)
    human = _upload_n(baseline_client, 1, start=4)[0]
    put = baseline_client.put(
        f"/api/images/{human}/label", json={"class_id": "samoyed"}
    )
    assert put.status_code == 200

    confidences = (0.40, 0.60, 0.80, 0.95)
    classes = ("boxer", "chihuahua", "pomeranian", "havanese")
    with _patch_infer(
        baseline_client,
        [
            _fold(class_id, confidence)
            for class_id, confidence in zip(classes, confidences, strict=True)
        ],
    ):
        generated = baseline_client.post("/api/suggestions", json={"refs": refs})
    assert generated.status_code == 200
    assert generated.json()["generated_count"] == 4

    accepted = baseline_client.post(
        "/api/suggestions/accept-by-threshold", json={"min_confidence": 0.6}
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"updated_count": 3}

    by_ref = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    kept = by_ref[refs[0]]
    assert kept["label"] is None
    assert kept["suggestion"]["confidence"] == pytest.approx(0.40)
    for ref, class_id, confidence in zip(
        refs[1:], classes[1:], confidences[1:], strict=True
    ):
        item = by_ref[ref]
        assert item["suggestion"] is None
        assert item["label"] == {"class_id": class_id, "source": "model_suggested"}
        assert confidence >= 0.6
    assert by_ref[human]["label"] == {"class_id": "samoyed", "source": "human"}
    assert by_ref[human]["suggestion"] is None


def test_ver_f_sug_004_suggestions_are_not_confirmed_labels(
    client: TestClient,
) -> None:
    """VER-F-SUG-004: 候補のみ 100 枚では確定ラベル 0。学習要求は受理されない。"""
    refs = _upload_n(client, 100)
    store = _client_store(client)
    model = store.insert_model(
        ref="44444444-4444-4444-8444-444444444444",
        version=1,
        builtin=False,
        created_at="2026-01-01T00:00:00Z",
    )
    store.upsert_suggestions(
        model_ref=model.ref,
        items=[
            SuggestionNew(
                image_ref=ref,
                class_id="boxer",
                confidence=0.5,
                created_at="2026-01-01T00:00:00Z",
            )
            for ref in refs
        ],
    )
    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["labeled_count"] == 0
    assert stats.json()["suggestion_count"] == 100
    images = client.get("/api/_state").json()["images"]
    assert len(images) == 100
    assert all(item["label"] is None for item in images)
    assert all(item["suggestion"] is not None for item in images)

    training = client.post("/api/jobs", json={})
    assert training.status_code >= 400
    assert training.status_code != 201


def test_unlabeled_set_without_refs(baseline_client: TestClient) -> None:
    unlabeled = _upload_n(baseline_client, 2)
    labeled = _upload_n(baseline_client, 1, start=2)[0]
    baseline_client.put(f"/api/images/{labeled}/label", json={"class_id": "boxer"})
    with _patch_infer(
        baseline_client,
        [_fold("chihuahua", 0.7), _fold("chihuahua", 0.7)],
    ):
        response = baseline_client.post("/api/suggestions")
    assert response.status_code == 200
    assert response.json() == {
        "generated_count": 2,
        "skipped_labeled_count": 0,
    }
    by_ref = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    for ref in unlabeled:
        assert by_ref[ref]["suggestion"]["class_id"] == "chihuahua"
    assert by_ref[labeled]["suggestion"] is None
    assert baseline_client.get("/api/_state").json()["inferences"] == []


def test_list_filters_and_orders_by_confidence(baseline_client: TestClient) -> None:
    refs = _upload_n(baseline_client, 3)
    with _patch_infer(
        baseline_client,
        [_fold("boxer", 0.2), _fold("boxer", 0.9), _fold("boxer", 0.5)],
    ):
        assert (
            baseline_client.post("/api/suggestions", json={"refs": refs}).status_code
            == 200
        )
    desc = baseline_client.get("/api/suggestions", params={"order": "desc"})
    assert desc.json()["total"] == 3
    assert [item["confidence"] for item in desc.json()["items"]] == pytest.approx(
        [0.9, 0.5, 0.2]
    )
    asc = baseline_client.get("/api/suggestions", params={"order": "asc"})
    assert [item["confidence"] for item in asc.json()["items"]] == pytest.approx(
        [0.2, 0.5, 0.9]
    )
    filtered = baseline_client.get(
        "/api/suggestions",
        params={"min_confidence": 0.5, "max_confidence": 0.9},
    )
    assert filtered.json()["total"] == 2
    assert [item["confidence"] for item in filtered.json()["items"]] == pytest.approx(
        [0.9, 0.5]
    )


def test_accept_specified_and_reject(
    baseline_client: TestClient,
) -> None:
    refs = _upload_n(baseline_client, 3)
    with _patch_infer(
        baseline_client,
        [_fold("boxer", 0.6), _fold("chihuahua", 0.7), _fold("havanese", 0.8)],
    ):
        baseline_client.post("/api/suggestions", json={"refs": refs})
    accepted = baseline_client.post("/api/suggestions/accept", json={"refs": [refs[1]]})
    assert accepted.status_code == 200
    assert accepted.json() == {"updated_count": 1}
    by_ref = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    assert by_ref[refs[1]]["label"] == {
        "class_id": "chihuahua",
        "source": "model_suggested",
    }
    assert by_ref[refs[1]]["suggestion"] is None
    assert by_ref[refs[0]]["suggestion"] is not None

    rejected = baseline_client.post("/api/suggestions/reject", json={"refs": [refs[0]]})
    assert rejected.status_code == 200
    assert rejected.json() == {"updated_count": 1}
    after = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    assert after[refs[0]]["suggestion"] is None
    assert after[refs[0]]["label"] is None

    missing = baseline_client.post("/api/suggestions/reject", json={"refs": [refs[0]]})
    assert missing.status_code == 404
    assert missing.json()["code"] == "suggestion_not_found"
    leftover_by_ref = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    assert leftover_by_ref[refs[2]]["suggestion"]["class_id"] == "havanese"


def test_generate_rejects_over_limit_and_missing_ref(
    baseline_client: TestClient,
) -> None:
    refs = _upload_n(baseline_client, 1)
    too_many = baseline_client.post(
        "/api/suggestions",
        json={"refs": [f"{i:08x}-0000-4000-8000-000000000000" for i in range(101)]},
    )
    assert too_many.status_code == 400
    assert too_many.json()["code"] == "validation_error"
    missing = baseline_client.post(
        "/api/suggestions",
        json={"refs": [refs[0], "00000000-0000-4000-8000-000000000099"]},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "image_not_found"
    assert baseline_client.get("/api/suggestions").json()["total"] == 0


def test_unlabeled_set_caps_at_100(baseline_client: TestClient) -> None:
    _upload_n(baseline_client, MAX_SUGGESTION_IMAGES + 1)
    results = [_fold("boxer", 0.9) for _ in range(MAX_SUGGESTION_IMAGES)]
    with _patch_infer(baseline_client, results):
        response = baseline_client.post("/api/suggestions")
    assert response.status_code == 200
    assert response.json()["generated_count"] == 100
    assert baseline_client.get("/api/suggestions").json()["total"] == 100
    unlabeled = [
        item
        for item in baseline_client.get("/api/_state").json()["images"]
        if item["suggestion"] is None
    ]
    assert len(unlabeled) == 1


def test_generate_all_labeled_returns_skip_count(baseline_client: TestClient) -> None:
    refs = _upload_n(baseline_client, 2)
    for ref in refs:
        baseline_client.put(f"/api/images/{ref}/label", json={"class_id": "boxer"})
    response = baseline_client.post("/api/suggestions", json={"refs": refs})
    assert response.status_code == 200
    assert response.json() == {
        "generated_count": 0,
        "skipped_labeled_count": 2,
    }


def test_list_rejects_inverted_confidence_range(baseline_client: TestClient) -> None:
    response = baseline_client.get(
        "/api/suggestions",
        params={"min_confidence": 0.8, "max_confidence": 0.2},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_accept_missing_image_is_404(baseline_client: TestClient) -> None:
    response = baseline_client.post(
        "/api/suggestions/accept",
        json={"refs": ["00000000-0000-4000-8000-000000000099"]},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "image_not_found"


def test_empty_refs_and_non_json_are_400(baseline_client: TestClient) -> None:
    empty = baseline_client.post("/api/suggestions", json={"refs": []})
    assert empty.status_code == 400
    assert empty.json()["code"] == "validation_error"
    invalid = baseline_client.post(
        "/api/suggestions",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "validation_error"


def test_generate_counts_labels_applied_during_infer(
    baseline_client: TestClient,
) -> None:
    """推論中に確定ラベルが付いた画像も skipped_labeled_count に含める。"""
    refs = _upload_n(baseline_client, 2)
    store = _client_store(baseline_client)
    app = baseline_client.app
    assert isinstance(app, FastAPI)
    runtime = app.state.baseline_runtime
    assert runtime is not None

    def infer(images: list[Any]) -> list[FoldResult]:
        store.upsert_label(refs[0], "samoyed", "human", "2026-01-01T00:00:00Z")
        return [_fold("boxer", 0.9) for _ in images]

    with patch.object(runtime, "infer_images", side_effect=infer):
        response = baseline_client.post("/api/suggestions", json={"refs": refs})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "generated_count": 1,
        "skipped_labeled_count": 1,
    }
    by_ref = {
        item["ref"]: item
        for item in baseline_client.get("/api/_state").json()["images"]
    }
    assert by_ref[refs[0]]["label"] == {"class_id": "samoyed", "source": "human"}
    assert by_ref[refs[0]]["suggestion"] is None
    assert by_ref[refs[1]]["suggestion"]["class_id"] == "boxer"


def test_runtime_openapi_includes_suggestion_create_body(client: TestClient) -> None:
    body = client.get("/openapi.json").json()
    post = body["paths"]["/api/suggestions"]["post"]
    assert "requestBody" in post
    schema = post["requestBody"]["content"]["application/json"]["schema"]
    dumped = str(schema) + str(body.get("components", {}).get("schemas", {}))
    assert "SuggestionCreateRequest" in dumped or "refs" in dumped
    schemas = body.get("components", {}).get("schemas", {})
    assert "SuggestionCreateRequest" in schemas
    assert "refs" in schemas["SuggestionCreateRequest"].get("properties", {})


def _cnn_artifact_bytes(tmp_path: Path) -> bytes:
    rng = np.random.default_rng(3)
    dest = tmp_path / "trained.onnx"
    export_cnn_onnx(
        rng.normal(0, 0.05, size=(8, 3, 3, 3)).astype(np.float32),
        np.zeros((8,), dtype=np.float32),
        rng.normal(0, 0.05, size=(16, 8, 3, 3)).astype(np.float32),
        np.zeros((16,), dtype=np.float32),
        rng.normal(0, 0.05, size=(N_CLASSES, 16)).astype(np.float32),
        np.zeros((N_CLASSES,), dtype=np.float32),
        dest,
    )
    return dest.read_bytes()


def test_trained_active_model_generates_suggestions(
    baseline_client: TestClient, tmp_path: Path
) -> None:
    """F014: 学習済モデルが有効でも候補を生成できる。"""
    refs = _upload_n(baseline_client, 2)
    store = _client_store(baseline_client)
    model = register_trained_model(
        store,
        created_at="2026-09-13T00:00:00Z",
        artifact_bytes=_cnn_artifact_bytes(tmp_path),
    )
    assert model.active is True
    assert model.builtin is False

    response = baseline_client.post("/api/suggestions", json={"refs": refs})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "generated_count": 2,
        "skipped_labeled_count": 0,
    }
    listed = baseline_client.get("/api/suggestions").json()["items"]
    assert len(listed) == 2
    assert {item["model_ref"] for item in listed} == {model.ref}
    assert all(item["class_id"] in CLASS_IDS for item in listed)
    assert all(0.0 <= item["confidence"] <= 1.0 for item in listed)
    assert baseline_client.get("/api/_state").json()["inferences"] == []


def _linear_artifact_bytes(tmp_path: Path) -> bytes:
    rng = np.random.default_rng(4)
    dest = tmp_path / "head.onnx"
    export_linear_onnx(
        rng.normal(0, 0.1, size=(N_CLASSES, EMBEDDING_DIM)).astype(np.float32),
        np.zeros((N_CLASSES,), dtype=np.float32),
        dest,
    )
    return dest.read_bytes()


def test_trained_session_reused_across_suggestion_requests(
    baseline_client: TestClient, tmp_path: Path
) -> None:
    refs = _upload_n(baseline_client, 2)
    store = _client_store(baseline_client)
    register_trained_model(
        store,
        created_at="2026-09-13T00:00:00Z",
        artifact_bytes=_cnn_artifact_bytes(tmp_path),
    )
    with patch(
        "faunalab.ml.session_cache.load_onnx_session", wraps=load_onnx_session
    ) as spy:
        first = baseline_client.post("/api/suggestions", json={"refs": [refs[0]]})
        second = baseline_client.post("/api/suggestions", json={"refs": [refs[1]]})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert spy.call_count == 1


def test_embedding_head_uses_startup_baseline_session(
    baseline_client: TestClient, tmp_path: Path
) -> None:
    refs = _upload_n(baseline_client, 1)
    store = _client_store(baseline_client)
    register_trained_model(
        store,
        created_at="2026-09-13T00:00:00Z",
        artifact_bytes=_linear_artifact_bytes(tmp_path),
    )
    with patch(
        "faunalab.ml.session_cache.load_onnx_session", wraps=load_onnx_session
    ) as spy:
        response = baseline_client.post("/api/suggestions", json={"refs": refs})
    assert response.status_code == 200, response.text
    assert response.json()["generated_count"] == 1
    assert spy.call_count == 1
    loaded = Path(spy.call_args.args[0])
    assert loaded.name == "model.onnx"
    listed = baseline_client.get("/api/suggestions").json()["items"]
    assert listed[0]["class_id"] in CLASS_IDS
