"""Inference API (F011).

Verification mapping:
- VER-F-INF-001: test_ver_f_inf_001_fails_without_active_model
- VER-F-INF-002: test_ver_f_inf_002_model_ref_frozen_and_score_sum
- VER-F-BASE-001: test_ver_f_base_001_http_inferences_match_expectations
- VER-F-BASE-002: test_ver_f_base_002_scores_other_mass_unmapped_low_conf
- VER-F-BASE-004: test_ver_f_base_004_class_map_swap_changes_inference
"""

from __future__ import annotations

import io
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.classes import CLASS_IDS
from faunalab.domain.images import MAX_IMAGE_BYTES
from faunalab.domain.inferences import (
    MAX_INFERENCE_IMAGES,
    SCORE_SUM_TOLERANCE,
    is_low_confidence,
    ranked_scores,
)
from faunalab.ml.baseline import sha256_file
from faunalab.ml.fold import FoldResult
from faunalab.persist.store import ImageNotFoundError, Store
from faunalab.settings import Settings, get_settings
from PIL import Image

REPO_ASSETS = Path(__file__).resolve().parents[2] / "assets"
FIXTURES = REPO_ASSETS / "fixtures"
EXPECTATIONS_PATH = FIXTURES / "baseline_expectations.json"
CONFIDENCE_TOLERANCE = 0.02
UNMAPPED = ("american_bulldog", "havanese")


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


def _image_bytes(
    fmt: str = "JPEG",
    *,
    size: tuple[int, int] = (32, 24),
    color: tuple[int, int, int] = (10, 20, 30),
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _post_files(client: TestClient, parts: list[tuple[str, bytes]]) -> Any:
    files = [("files", (name, data, "image/jpeg")) for name, data in parts]
    return client.post("/api/inferences", files=files)


def _client_store(client: TestClient) -> Store:
    app = client.app
    assert isinstance(app, FastAPI)
    store = app.state.store
    assert isinstance(store, Store)
    return store


def test_ranked_scores_are_descending_with_display_order_tiebreak() -> None:
    scores = {class_id: 0.1 for class_id in CLASS_IDS}
    scores["boxer"] = 0.3
    scores["samoyed"] = 0.3
    ranked = ranked_scores(scores)
    assert [item["class_id"] for item in ranked][:2] == ["samoyed", "boxer"]
    assert ranked[0]["confidence"] == 0.3


def test_low_confidence_uses_thresholds_and_uniform_fallback() -> None:
    result = FoldResult(
        scores=dict.fromkeys(CLASS_IDS, 0.125),
        other_mass=0.9,
        uniform_fallback=False,
        top_class_id="samoyed",
        top_confidence=0.4,
    )
    assert is_low_confidence(
        result,
        confidence_threshold=0.5,
        other_mass_threshold=0.5,
        other_mass=0.9,
    )
    high = FoldResult(
        scores=dict.fromkeys(CLASS_IDS, 0.125),
        other_mass=0.1,
        uniform_fallback=False,
        top_class_id="samoyed",
        top_confidence=0.9,
    )
    assert not is_low_confidence(
        high,
        confidence_threshold=0.5,
        other_mass_threshold=0.5,
        other_mass=0.1,
    )
    uniform = FoldResult(
        scores=dict.fromkeys(CLASS_IDS, 0.125),
        other_mass=1.0,
        uniform_fallback=True,
        top_class_id="samoyed",
        top_confidence=0.125,
    )
    assert is_low_confidence(
        uniform,
        confidence_threshold=0.5,
        other_mass_threshold=0.99,
        other_mass=0.1,
    )


def test_ver_f_inf_001_fails_without_active_model(client: TestClient) -> None:
    """VER-F-INF-001: ベースライン無し・学習済なしでは推論が失敗する。"""
    response = _post_files(client, [("a.jpg", _image_bytes())])
    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["code"] == "no_active_model"
    assert body["status"] == 422
    assert client.get("/api/_state").json()["inferences"] == []


def test_ver_f_base_001_http_inferences_match_expectations(
    baseline_client: TestClient,
) -> None:
    """VER-F-BASE-001: フィクスチャを HTTP 推論し期待値と照合する。"""
    payload = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    items = payload["items"]
    mismatches: list[str] = []
    for start in range(0, len(items), MAX_INFERENCE_IMAGES):
        chunk = items[start : start + MAX_INFERENCE_IMAGES]
        parts = [
            (Path(item["file"]).name, (FIXTURES / item["file"]).read_bytes())
            for item in chunk
        ]
        response = _post_files(baseline_client, parts)
        assert response.status_code == 200, response.text
        results = response.json()["items"]
        assert len(results) == len(chunk)
        for item, result in zip(chunk, results, strict=True):
            top_ok = result["top_class_id"] == item["expected_top_class_id"]
            conf_ok = (
                abs(result["top_confidence"] - float(item["expected_top_confidence"]))
                <= CONFIDENCE_TOLERANCE
            )
            if not top_ok or not conf_ok:
                mismatches.append(
                    f"{item['file']}: got {result['top_class_id']} "
                    f"{result['top_confidence']:.4f}, expected "
                    f"{item['expected_top_class_id']} "
                    f"{item['expected_top_confidence']}"
                )
    assert mismatches == []


def test_ver_f_base_002_scores_other_mass_unmapped_low_conf(
    baseline_client: TestClient,
) -> None:
    """VER-F-BASE-002: 8 クラス・総和・other_mass・未収録 0・非犬は低信頼。"""
    sample = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))["items"][0]
    path = FIXTURES / sample["file"]
    response = _post_files(
        baseline_client, [(path.name, path.read_bytes())]
    )
    assert response.status_code == 200
    result = response.json()["items"][0]
    scores = result["scores"]
    assert len(scores) == 8
    assert {item["class_id"] for item in scores} == set(CLASS_IDS)
    confidences = [item["confidence"] for item in scores]
    assert confidences == sorted(confidences, reverse=True)
    assert abs(sum(confidences) - 1.0) <= SCORE_SUM_TOLERANCE
    assert result["other_mass"] is not None
    assert 0.0 <= result["other_mass"] <= 1.0
    by_class = {item["class_id"]: item["confidence"] for item in scores}
    for class_id in UNMAPPED:
        assert by_class[class_id] == 0.0

    blank = _post_files(
        baseline_client,
        [("blank.jpg", _image_bytes(size=(256, 256), color=(200, 200, 200)))],
    )
    assert blank.status_code == 200
    blank_item = blank.json()["items"][0]
    assert blank_item["low_confidence"] is True
    assert isinstance(blank_item["other_mass"], float)


def test_ver_f_inf_002_model_ref_frozen_and_score_sum(
    baseline_client: TestClient,
) -> None:
    """VER-F-INF-002: 有効化切替後も過去の model_ref は不変。総和は 1.0±0.001。"""
    jpeg = _image_bytes(color=(1, 2, 3))
    created = _post_files(baseline_client, [("a.jpg", jpeg)])
    assert created.status_code == 200
    item = created.json()["items"][0]
    original_model_ref = item["model_ref"]
    score_sum = sum(score["confidence"] for score in item["scores"])
    assert abs(score_sum - 1.0) <= SCORE_SUM_TOLERANCE

    store = _client_store(baseline_client)
    other_ref = str(uuid.uuid4())
    store.insert_model(
        ref=other_ref,
        version=1,
        builtin=False,
        created_at="2026-09-13T00:00:00Z",
    )
    activated = store.activate_model(other_ref)
    assert activated is not None
    assert activated.active is True
    assert activated.ref == other_ref
    models = baseline_client.get("/api/_state").json()["models"]
    active = [model for model in models if model["active"]]
    assert len(active) == 1
    assert active[0]["ref"] == other_ref

    observed = baseline_client.get("/api/_state").json()["inferences"]
    matching = [row for row in observed if row["ref"] == item["ref"]]
    assert len(matching) == 1
    assert matching[0]["model_ref"] == original_model_ref
    listed = baseline_client.get("/api/inferences").json()["items"]
    assert listed[0]["ref"] == item["ref"]
    assert listed[0]["model_ref"] == original_model_ref


def test_new_file_is_unassigned_and_unlabeled(baseline_client: TestClient) -> None:
    """REQ-F-INF-006: 新規投入画像は unassigned・ラベル無し。"""
    response = _post_files(baseline_client, [("fresh.jpg", _image_bytes())])
    assert response.status_code == 200
    image_ref = response.json()["items"][0]["image_ref"]
    images = {
        row["ref"]: row for row in baseline_client.get("/api/_state").json()["images"]
    }
    assert images[image_ref]["split"] == "unassigned"
    assert images[image_ref]["label"] is None


def test_registered_ref_and_mixed_request(baseline_client: TestClient) -> None:
    jpeg = _image_bytes(color=(9, 9, 9))
    uploaded = baseline_client.post(
        "/api/images",
        files=[("files", ("reg.jpg", jpeg, "image/jpeg"))],
    )
    assert uploaded.status_code == 200
    image_ref = uploaded.json()["items"][0]["ref"]
    extra = _image_bytes(color=(3, 4, 5))
    response = baseline_client.post(
        "/api/inferences",
        files=[("files", ("new.jpg", extra, "image/jpeg"))],
        data={"refs": image_ref},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[1]["image_ref"] == image_ref
    json_only = baseline_client.post(
        "/api/inferences", json={"refs": [image_ref]}
    )
    assert json_only.status_code == 200
    assert json_only.json()["items"][0]["image_ref"] == image_ref


def test_over_limit_and_missing_ref(baseline_client: TestClient) -> None:
    too_many = [
        (f"n{index}.jpg", _image_bytes(color=(index, 0, 0)))
        for index in range(MAX_INFERENCE_IMAGES + 1)
    ]
    over = _post_files(baseline_client, too_many)
    assert over.status_code == 400
    assert over.json()["code"] == "validation_error"

    missing = baseline_client.post(
        "/api/inferences",
        json={"refs": [str(uuid.uuid4())]},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "image_not_found"


def test_unsupported_and_oversize(baseline_client: TestClient) -> None:
    fake = baseline_client.post(
        "/api/inferences",
        files=[("files", ("x.txt", b"not-an-image", "text/plain"))],
    )
    assert fake.status_code == 415
    assert fake.json()["code"] == "unsupported_media_type"

    oversize = _image_bytes(size=(8, 8)) + (b"\x00" * (MAX_IMAGE_BYTES + 1))
    huge = baseline_client.post(
        "/api/inferences",
        files=[("files", ("big.jpg", oversize, "image/jpeg"))],
        headers={"content-length": str(len(oversize) + 200)},
    )
    assert huge.status_code == 413
    assert huge.json()["code"] == "payload_too_large"


def test_history_survives_restart_and_is_newest_first(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, _copy_baseline(tmp_path))
    with TestClient(create_app(settings)) as client:
        first = _post_files(client, [("a.jpg", _image_bytes(color=(1, 0, 0)))])
        assert first.status_code == 200
        ref_a = first.json()["items"][0]["ref"]
        second = _post_files(client, [("b.jpg", _image_bytes(color=(0, 1, 0)))])
        assert second.status_code == 200
        ref_b = second.json()["items"][0]["ref"]
        listed = client.get("/api/inferences").json()
        assert listed["total"] == 2
        listed_refs = [item["ref"] for item in listed["items"]]
        assert set(listed_refs) == {ref_a, ref_b}
    with TestClient(create_app(settings)) as again:
        body = again.get("/api/_state").json()["inferences"]
        assert {item["ref"] for item in body} == {ref_a, ref_b}
        page = again.get("/api/inferences").json()
        assert page["total"] == 2
        created = [item["created_at"] for item in page["items"]]
        assert created == sorted(created, reverse=True)


def test_duplicate_file_reuses_existing_image(baseline_client: TestClient) -> None:
    jpeg = _image_bytes(color=(7, 8, 9))
    first = _post_files(baseline_client, [("one.jpg", jpeg)])
    second = _post_files(baseline_client, [("copy.jpg", jpeg)])
    assert first.status_code == 200
    assert second.status_code == 200
    first_image = first.json()["items"][0]["image_ref"]
    second_image = second.json()["items"][0]["image_ref"]
    assert first_image == second_image
    images = baseline_client.get("/api/_state").json()["images"]
    assert len(images) == 1


def test_json_blank_ref_is_validation_error(baseline_client: TestClient) -> None:
    response = baseline_client.post("/api/inferences", json={"refs": ["   "]})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert baseline_client.get("/api/_state").json()["inferences"] == []


def test_history_insert_failure_rolls_back_new_images(
    baseline_client: TestClient,
) -> None:
    jpeg = _image_bytes(color=(11, 12, 13))
    with patch.object(Store, "insert_inferences", side_effect=ImageNotFoundError):
        response = _post_files(baseline_client, [("a.jpg", jpeg)])
    assert response.status_code == 404
    state = baseline_client.get("/api/_state").json()
    assert state["images"] == []
    assert state["inferences"] == []


def test_insert_failure_keeps_already_registered_image(
    baseline_client: TestClient,
) -> None:
    jpeg = _image_bytes(color=(14, 15, 16))
    uploaded = baseline_client.post(
        "/api/images",
        files=[("files", ("r.jpg", jpeg, "image/jpeg"))],
    )
    assert uploaded.status_code == 200
    existing = uploaded.json()["items"][0]["ref"]
    extra = _image_bytes(color=(20, 21, 22))
    with patch.object(Store, "insert_inferences", side_effect=ImageNotFoundError):
        response = baseline_client.post(
            "/api/inferences",
            files=[("files", ("new.jpg", extra, "image/jpeg"))],
            data={"refs": existing},
        )
    assert response.status_code == 404
    images = baseline_client.get("/api/_state").json()["images"]
    assert [row["ref"] for row in images] == [existing]
    assert baseline_client.get("/api/_state").json()["inferences"] == []


def _fingerprint(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = sha256_file(path)
    return hashes


def _swap_samoyed_boxer_and_retarget(assets: Path) -> None:
    class_map_path = assets / "baseline" / "class_map.json"
    payload = json.loads(class_map_path.read_text(encoding="utf-8"))
    payload["classes"]["samoyed"], payload["classes"]["boxer"] = (
        payload["classes"]["boxer"],
        payload["classes"]["samoyed"],
    )
    class_map_path.write_text(json.dumps(payload), encoding="utf-8")
    digest = sha256_file(class_map_path)
    manifest_path = assets / "baseline" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["file"] == "class_map.json":
            entry["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_ver_f_base_004_class_map_swap_changes_inference(tmp_path: Path) -> None:
    """VER-F-BASE-004: class_map を入れ替えると推論が変わり、assets/ は不変。"""

    sample = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))["items"][0]
    assert sample["expected_top_class_id"] == "samoyed"
    image_bytes = (FIXTURES / sample["file"]).read_bytes()
    before = _fingerprint(REPO_ASSETS)

    original_assets = _copy_baseline(tmp_path / "orig")
    original_settings = _settings(tmp_path / "orig-data", original_assets)
    with TestClient(create_app(original_settings)) as client:
        first = _post_files(client, [(Path(sample["file"]).name, image_bytes)])
        assert first.status_code == 200, first.text
        original_top = first.json()["items"][0]["top_class_id"]
        assert original_top == "samoyed"

    swapped_assets = _copy_baseline(tmp_path / "swap")
    _swap_samoyed_boxer_and_retarget(swapped_assets)
    swapped_settings = _settings(tmp_path / "swap-data", swapped_assets)
    with TestClient(create_app(swapped_settings)) as client:
        second = _post_files(client, [(Path(sample["file"]).name, image_bytes)])
        assert second.status_code == 200, second.text
        swapped_top = second.json()["items"][0]["top_class_id"]
    assert swapped_top != original_top
    assert swapped_top == "boxer"
    assert _fingerprint(REPO_ASSETS) == before
    get_settings.cache_clear()
