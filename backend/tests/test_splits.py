"""Dataset split API (F009).

Verification mapping:
- VER-F-DS-001 (REQ-F-DS-002): test_ver_f_ds_001_stratified_within_one
- VER-F-DS-002 (REQ-F-DS-003): test_ver_f_ds_002_same_seed_matches
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.classes import CLASS_IDS
from faunalab.persist.store import Store


def _app_store(client: TestClient) -> Store:
    app = client.app
    assert isinstance(app, FastAPI)
    store = app.state.store
    assert isinstance(store, Store)
    return store


def _seed_labeled(store: Store, per_class: int, *, unlabeled: int = 0) -> None:
    created = "2024-06-01T00:00:00Z"
    serial = 0
    for class_id in CLASS_IDS:
        for index in range(per_class):
            serial += 1
            payload = f"{class_id}:{index}".encode()
            digest = sha256(payload).hexdigest()
            ref = f"00000000-0000-4000-8000-{serial:012d}"
            store.insert_image(
                ref=ref,
                sha256=digest,
                original_name=f"{class_id}_{index}.jpg",
                size_bytes=len(payload),
                width=8,
                height=8,
                path=f"images/{digest}.jpg",
                created_at=created,
            )
            store.upsert_label(ref, class_id, "human", created)
    for index in range(unlabeled):
        serial += 1
        payload = f"unlabeled:{index}".encode()
        digest = sha256(payload).hexdigest()
        ref = f"00000000-0000-4000-8000-{serial:012d}"
        store.insert_image(
            ref=ref,
            sha256=digest,
            original_name=f"u_{index}.jpg",
            size_bytes=len(payload),
            width=8,
            height=8,
            path=f"images/{digest}.jpg",
            created_at=created,
        )


def _counts_by_class_split(images: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {
        class_id: {"train": 0, "val": 0, "test": 0, "unassigned": 0}
        for class_id in CLASS_IDS
    }
    for item in images:
        label = item["label"]
        if label is None:
            continue
        counts[label["class_id"]][item["split"]] += 1
    return counts


def test_ver_f_ds_001_stratified_within_one(client: TestClient) -> None:
    """VER-F-DS-001: 各クラス 100 枚、比率 0.7/0.15/0.15 で ±1 枚。"""
    store = _app_store(client)
    _seed_labeled(store, per_class=100)
    response = client.post(
        "/api/splits",
        json={"train_ratio": 0.7, "val_ratio": 0.15, "test_ratio": 0.15, "seed": 42},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assigned_count"] == 800
    assert body["unassigned_count"] == 0
    images = client.get("/api/_state").json()["images"]
    counts = _counts_by_class_split(images)
    for class_id in CLASS_IDS:
        per = counts[class_id]
        assert sum(per.values()) == 100
        assert abs(per["train"] - 70) <= 1
        assert abs(per["val"] - 15) <= 1
        assert abs(per["test"] - 15) <= 1
        assert per["unassigned"] == 0


def test_ver_f_ds_002_same_seed_matches(client: TestClient) -> None:
    """VER-F-DS-002: 同一シードは一致し、異なるシードでは一致しない。"""
    store = _app_store(client)
    _seed_labeled(store, per_class=20)
    first = client.post("/api/splits", json={"seed": 42})
    assert first.status_code == 200
    splits_a = {
        item["ref"]: item["split"]
        for item in client.get("/api/_state").json()["images"]
    }
    second = client.post("/api/splits", json={"seed": 42})
    assert second.status_code == 200
    splits_b = {
        item["ref"]: item["split"]
        for item in client.get("/api/_state").json()["images"]
    }
    assert splits_a == splits_b
    third = client.post("/api/splits", json={"seed": 99})
    assert third.status_code == 200
    splits_c = {
        item["ref"]: item["split"]
        for item in client.get("/api/_state").json()["images"]
    }
    assert splits_a != splits_c


def test_unlabeled_images_stay_unassigned(client: TestClient) -> None:
    """REQ-F-DS-004: 未ラベルは unassigned のまま。"""
    store = _app_store(client)
    _seed_labeled(store, per_class=2, unlabeled=5)
    response = client.post("/api/splits", json={})
    assert response.status_code == 200
    assert response.json()["assigned_count"] == 16
    assert response.json()["unassigned_count"] == 5
    unlabeled = [
        item
        for item in client.get("/api/_state").json()["images"]
        if item["label"] is None
    ]
    assert len(unlabeled) == 5
    assert {item["split"] for item in unlabeled} == {"unassigned"}


def test_ratio_sum_not_one_is_400(client: TestClient) -> None:
    response = client.post(
        "/api/splits",
        json={"train_ratio": 0.5, "val_ratio": 0.5, "test_ratio": 0.5},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["code"] == "validation_error"


def test_default_seed_and_ratios(client: TestClient) -> None:
    store = _app_store(client)
    _seed_labeled(store, per_class=5)
    response = client.post("/api/splits", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["seed"] == 42
    assert body["train_ratio"] == 0.7
    assert body["val_ratio"] == 0.15
    assert body["test_ratio"] == 0.15
