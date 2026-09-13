"""Baseline version 0 registration (REQ-F-BASE-001 / 005 / 006 / 007 / 009 / 011).

Verification mapping:
- VER-F-BASE-003: test_ver_f_base_003_five_startup_states
- MANIFEST SHA-256: test_checksum_mismatch_is_rejected
- class_map keys: test_class_map_missing_key_is_rejected
- REQ-F-BASE-009: test_class_map_is_read_from_file
- REQ-F-BASE-011: test_ver_f_base_003_five_startup_states (repo assets unchanged)
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.domain.classes import CLASS_IDS
from faunalab.ml.baseline import inspect_baseline_assets, load_class_map, sha256_file
from faunalab.ml.fold import fold_logits
from faunalab.persist.store import DB_FILENAME
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


def _copy_assets(tmp_path: Path) -> Path:
    dest = tmp_path / "copied-assets"
    shutil.copytree(REPO_ASSETS, dest)
    return dest


def _flip_last_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-1] ^= 0x01
    path.write_bytes(bytes(data))


def _fingerprint(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = sha256_file(path)
    return hashes


def _drop_class_and_retarget_manifest(assets: Path, class_id: str) -> None:
    class_map_path = assets / "baseline" / "class_map.json"
    payload = json.loads(class_map_path.read_text(encoding="utf-8"))
    del payload["classes"][class_id]
    class_map_path.write_text(json.dumps(payload), encoding="utf-8")
    digest = sha256_file(class_map_path)
    manifest_path = assets / "baseline" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["file"] == "class_map.json":
            entry["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _models(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/_state").json()["models"]


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (16, 16), (1, 2, 3))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_inspect_accepts_repo_assets() -> None:
    inspection = inspect_baseline_assets(REPO_ASSETS)
    assert inspection.ok
    assert inspection.class_map is not None
    assert set(inspection.class_map) == set(CLASS_IDS)
    assert inspection.class_map["american_bulldog"] == ()
    assert inspection.class_map["havanese"] == ()
    assert inspection.model_path is not None
    assert inspection.model_path.name == "model.onnx"


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    assets = _copy_assets(tmp_path)
    _flip_last_byte(assets / "baseline" / "model.onnx")
    inspection = inspect_baseline_assets(assets)
    assert not inspection.ok
    assert "sha256" in inspection.reason


def test_hash_read_error_does_not_abort_inspect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _copy_assets(tmp_path)

    def boom(_path: Path) -> str:
        raise OSError("simulated io error")

    monkeypatch.setattr("faunalab.ml.baseline.sha256_file", boom)
    inspection = inspect_baseline_assets(assets)
    assert not inspection.ok
    assert "unreadable" in inspection.reason


def test_class_map_must_be_listed_in_manifest(tmp_path: Path) -> None:
    assets = _copy_assets(tmp_path)
    manifest_path = assets / "baseline" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = [
        entry
        for entry in manifest["files"]
        if entry["file"] != "class_map.json"
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    inspection = inspect_baseline_assets(assets)
    assert not inspection.ok
    assert "class_map.json" in inspection.reason


def test_duplicate_manifest_file_is_rejected(tmp_path: Path) -> None:
    assets = _copy_assets(tmp_path)
    manifest_path = assets / "baseline" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    class_map_entry = next(
        entry for entry in manifest["files"] if entry["file"] == "class_map.json"
    )
    manifest["files"].append(class_map_entry)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    inspection = inspect_baseline_assets(assets)
    assert not inspection.ok
    assert "more than once" in inspection.reason


def test_class_map_missing_key_is_rejected(tmp_path: Path) -> None:
    assets = _copy_assets(tmp_path)
    _drop_class_and_retarget_manifest(assets, "havanese")
    inspection = inspect_baseline_assets(assets)
    assert not inspection.ok
    assert "keys mismatch" in inspection.reason


def test_duplicate_imagenet_index_is_rejected(tmp_path: Path) -> None:
    assets = _copy_assets(tmp_path)
    class_map_path = assets / "baseline" / "class_map.json"
    payload = json.loads(class_map_path.read_text(encoding="utf-8"))
    payload["classes"]["boxer"] = payload["classes"]["samoyed"]
    class_map_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded, error = load_class_map(class_map_path)
    assert loaded is None
    assert error is not None
    assert "mapped to both" in error


def test_class_map_is_read_from_file(tmp_path: Path) -> None:
    """REQ-F-BASE-009: swapping the file changes fold-in, so it is not hard-coded."""

    original = json.loads(
        (REPO_ASSETS / "baseline" / "class_map.json").read_text(encoding="utf-8")
    )
    swapped = json.loads(json.dumps(original))
    swapped["classes"]["samoyed"], swapped["classes"]["boxer"] = (
        swapped["classes"]["boxer"],
        swapped["classes"]["samoyed"],
    )
    path = tmp_path / "class_map.json"
    path.write_text(json.dumps(swapped), encoding="utf-8")
    loaded, error = load_class_map(path)
    assert error is None
    assert loaded is not None
    logits = np.full(1000, -40.0)
    logits[258] = 12.0
    original_map = {
        class_id: tuple(indices)
        for class_id, indices in original["classes"].items()
    }
    from_file = fold_logits(logits, loaded)
    from_original = fold_logits(logits, original_map)
    assert from_original.top_class_id == "samoyed"
    assert from_file.top_class_id == "boxer"


def test_ver_f_base_003_five_startup_states(
    tmp_path: Path, caplog: Any
) -> None:
    """VER-F-BASE-003: five asset states; only the intact copy registers version 0."""

    before = _fingerprint(REPO_ASSETS)
    caplog.set_level(logging.WARNING, logger="faunalab.ml.baseline")

    with TestClient(create_app(_settings(tmp_path / "ok", REPO_ASSETS))) as client:
        models = _models(client)
        assert len(models) == 1
        assert models[0]["version"] == 0
        assert models[0]["builtin"] is True
        assert models[0]["active"] is True
        assert models[0]["metrics"] is None
        assert models[0]["ref"]

    flipped_weights = _copy_assets(tmp_path / "flip-weight")
    _flip_last_byte(flipped_weights / "baseline" / "model.onnx")
    with TestClient(
        create_app(_settings(tmp_path / "bad-weight", flipped_weights))
    ) as client:
        assert _models(client) == []

    flipped_map = _copy_assets(tmp_path / "flip-map")
    _flip_last_byte(flipped_map / "baseline" / "class_map.json")
    with TestClient(
        create_app(_settings(tmp_path / "bad-map", flipped_map))
    ) as client:
        assert _models(client) == []

    dropped = _copy_assets(tmp_path / "drop-class")
    _drop_class_and_retarget_manifest(dropped, "chihuahua")
    with TestClient(
        create_app(_settings(tmp_path / "missing-class", dropped))
    ) as client:
        assert _models(client) == []

    missing = tmp_path / "no-assets"
    with TestClient(create_app(_settings(tmp_path / "gone", missing))) as client:
        assert _models(client) == []
        uploaded = client.post(
            "/api/images",
            files=[("files", ("a.jpg", _tiny_jpeg(), "image/jpeg"))],
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["items"][0]["ok"] is True
        assert len(client.get("/api/_state").json()["images"]) == 1

    assert _fingerprint(REPO_ASSETS) == before
    assert "not registered" in caplog.text


def test_restart_keeps_version_zero_ref(tmp_path: Path) -> None:
    settings = _settings(tmp_path, REPO_ASSETS)
    with TestClient(create_app(settings)) as client:
        first = _models(client)[0]["ref"]
    with TestClient(create_app(settings)) as client:
        second = _models(client)[0]
    assert second["ref"] == first
    assert second["active"] is True


def test_does_not_steal_active_from_trained_model(tmp_path: Path) -> None:
    settings = _settings(tmp_path, REPO_ASSETS)
    with TestClient(create_app(settings)) as client:
        assert _models(client)[0]["active"] is True
    conn = sqlite3.connect(settings.data_dir / DB_FILENAME)
    conn.execute("UPDATE models SET active = 0 WHERE version = 0")
    conn.execute(
        """
        INSERT INTO models (ref, version, builtin, active, created_at)
        VALUES (?, 1, 0, 1, ?)
        """,
        ("11111111-bbbb-4ccc-8ddd-eeeeeeeeeeee", "2026-09-13T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    with TestClient(create_app(settings)) as client:
        models = {item["version"]: item for item in _models(client)}
    assert models[0]["active"] is False
    assert models[1]["active"] is True


def test_builtin_ref_is_uuid_v4(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path, REPO_ASSETS))) as client:
        ref = _models(client)[0]["ref"]
    parts = ref.split("-")
    assert len(ref) == 36
    assert len(parts) == 5
    assert parts[2][0] == "4"
    assert parts[3][0] in "89ab"


def test_missing_assets_logs_warning(tmp_path: Path, caplog: Any) -> None:
    caplog.set_level(logging.WARNING, logger="faunalab.ml.baseline")
    with TestClient(create_app(_settings(tmp_path, tmp_path / "absent"))):
        pass
    assert "assets directory missing" in caplog.text
