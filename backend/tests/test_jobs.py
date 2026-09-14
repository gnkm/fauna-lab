"""Training jobs (F014 / REQ-F-TRN-001〜017, REQ-F-MDL-002/004).

Verification mapping (automatic tests use reduced epochs; a full 10-epoch
run on the sample set is left to manual / a separate job):

- VER-F-TRN-001: test_ver_f_trn_001_start_returns_within_one_second
- VER-F-TRN-002: test_ver_f_trn_002_precondition_and_single_running
- VER-F-TRN-003: test_ver_f_trn_003_transitions_and_cancel
- VER-F-TRN-004: test_ver_f_trn_004_epoch_progress_and_logs
- VER-F-TRN-005: test_ver_f_trn_005_baseline_paths_and_thirty_images
- VER-F-TRN-006: test_ver_f_trn_006_reproducible_test_accuracy
- VER-F-TRN-007: test_ver_f_trn_007_restart_fails_running
- VER-F-MDL-002 (first trained activates, second does not):
  test_ver_f_mdl_002_first_trained_activates_second_does_not

Long / full-epoch training is not required in CI. Chance-level (0.125) is
checked on the reduced-epoch baseline-head path.
"""

from __future__ import annotations

import io
import sqlite3
import subprocess
import sys
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.api.jobs import JobCreateRequest
from faunalab.domain.jobs import JobParams
from faunalab.jobs.supervisor import start_worker, stop_worker
from faunalab.persist.store import DB_FILENAME, TRAINED_ONNX_NAME, Store
from faunalab.settings import Settings, get_settings
from PIL import Image
from pydantic import ValidationError

REPO_ASSETS = Path(__file__).resolve().parents[2] / "assets"
TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELED"})
ALLOWED_TRANSITIONS = {
    "QUEUED": frozenset({"RUNNING", "CANCELED"}),
    "RUNNING": frozenset({"SUCCEEDED", "FAILED", "CANCELED"}),
}


def _settings(tmp_path: Path, assets_dir: Path) -> Settings:
    get_settings.cache_clear()
    return Settings(
        data_dir=tmp_path / "data",
        assets_dir=assets_dir,
        web_dist_dir=tmp_path / "missing-dist",
    )


def _app_store(client: TestClient) -> Store:
    app = client.app
    assert isinstance(app, FastAPI)
    store = app.state.store
    assert isinstance(store, Store)
    return store


def _jpeg(color: tuple[int, int, int], salt: int = 0) -> bytes:
    image = Image.new("RGB", (64, 48), color)
    for offset in range(16):
        x = offset % 64
        y = offset // 4
        image.putpixel(
            (x, y),
            (
                (color[0] + salt + offset) % 256,
                (color[1] + salt * 3) % 256,
                (color[2] + salt * 7 + offset * 11) % 256,
            ),
        )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _plant(
    client: TestClient,
    *,
    class_id: str,
    split: str,
    count: int,
    color: tuple[int, int, int],
    salt0: int = 0,
) -> list[str]:
    refs: list[str] = []
    for index in range(count):
        payload = _jpeg(color, salt0 + index)
        filename = f"{class_id}-{split}-{salt0}-{index}.png"
        uploaded = client.post(
            "/api/images",
            files=[("files", (filename, payload, "image/png"))],
        )
        assert uploaded.status_code == 200, uploaded.text
        item = uploaded.json()["items"][0]
        assert item["ok"] is True
        ref = str(item["ref"])
        labeled = client.put(
            f"/api/images/{ref}/label",
            json={"class_id": class_id, "source": "human"},
        )
        assert labeled.status_code == 200
        refs.append(ref)
    assignments = {ref: split for ref in refs}
    existing = {
        item["ref"]: item["split"]
        for item in client.get("/api/_state").json()["images"]
        if item["label"] is not None
    }
    existing.update(assignments)
    _app_store(client).apply_split_assignments(existing)
    return refs


def _ready_baseline_set(
    client: TestClient,
    *,
    train_a: int = 6,
    train_b: int = 6,
    val: int = 1,
    test: int = 2,
) -> None:
    _plant(
        client,
        class_id="samoyed",
        split="train",
        count=train_a,
        color=(240, 240, 240),
    )
    _plant(
        client,
        class_id="boxer",
        split="train",
        count=train_b,
        color=(10, 10, 10),
        salt0=50,
    )
    _plant(
        client,
        class_id="samoyed",
        split="val",
        count=val,
        color=(230, 230, 230),
        salt0=80,
    )
    if test:
        _plant(
            client,
            class_id="samoyed",
            split="test",
            count=test // 2 or 1,
            color=(220, 220, 220),
            salt0=90,
        )
        if test > 1:
            _plant(
                client,
                class_id="boxer",
                split="test",
                count=test - test // 2,
                color=(20, 10, 10),
                salt0=100,
            )


def wait_job(client: TestClient, ref: str, *, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{ref}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert isinstance(body, dict)
        last = body
        if last["status"] in TERMINAL:
            return last
        time.sleep(0.1)
    raise AssertionError(f"job {ref} did not finish: {last}")


def _state(client: TestClient) -> dict[str, Any]:
    return client.get("/api/_state").json()


@pytest.fixture
def baseline_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _settings(tmp_path, REPO_ASSETS)
    with TestClient(create_app(settings)) as client:
        yield client
    get_settings.cache_clear()


def test_ver_f_trn_001_start_returns_within_one_second(
    baseline_client: TestClient,
) -> None:
    """VER-F-TRN-001: 開始は 1 秒以内。status は QUEUED または RUNNING。"""
    _ready_baseline_set(baseline_client)
    started = time.perf_counter()
    response = baseline_client.post(
        "/api/jobs", json={"epochs": 1, "augmentation": False}
    )
    elapsed = time.perf_counter() - started
    assert elapsed <= 1.0
    assert response.status_code == 201
    assert response.headers["location"].startswith("/api/jobs/")
    body = response.json()
    assert body["status"] in {"QUEUED", "RUNNING"}
    jobs = _state(baseline_client)["jobs"]
    match = next(item for item in jobs if item["ref"] == body["ref"])
    assert match["status"] in {"QUEUED", "RUNNING"}
    finished = wait_job(baseline_client, body["ref"])
    assert finished["status"] == "SUCCEEDED"


def test_ver_f_trn_002_precondition_and_single_running(
    baseline_client: TestClient,
) -> None:
    """VER-F-TRN-002: 9 枚ではジョブが増えない。RUNNING は同時 1 件。"""
    _plant(
        baseline_client,
        class_id="samoyed",
        split="train",
        count=5,
        color=(200, 200, 200),
    )
    _plant(
        baseline_client,
        class_id="boxer",
        split="train",
        count=4,
        color=(5, 5, 5),
        salt0=20,
    )
    before = len(_state(baseline_client)["jobs"])
    refused = baseline_client.post("/api/jobs", json={"epochs": 1})
    assert refused.status_code == 422
    assert refused.headers["content-type"].startswith(PROBLEM_JSON)
    assert refused.json()["code"] == "training_precondition"
    assert len(_state(baseline_client)["jobs"]) == before

    _plant(
        baseline_client,
        class_id="boxer",
        split="train",
        count=2,
        color=(8, 5, 5),
        salt0=40,
    )
    _plant(
        baseline_client,
        class_id="samoyed",
        split="val",
        count=1,
        color=(210, 200, 200),
        salt0=60,
    )
    first = baseline_client.post("/api/jobs", json={"epochs": 6, "augmentation": False})
    second = baseline_client.post(
        "/api/jobs", json={"epochs": 1, "augmentation": False}
    )
    assert first.status_code == 201
    assert second.status_code == 201
    deadline = time.monotonic() + 30
    seen_running = 0
    while time.monotonic() < deadline:
        jobs = _state(baseline_client)["jobs"]
        running = [item for item in jobs if item["status"] == "RUNNING"]
        assert len(running) <= 1
        seen_running = max(seen_running, len(running))
        statuses = {item["ref"]: item["status"] for item in jobs}
        if all(status in TERMINAL for status in statuses.values()):
            break
        time.sleep(0.1)
    wait_job(baseline_client, first.json()["ref"])
    wait_job(baseline_client, second.json()["ref"])
    jobs = _state(baseline_client)["jobs"]
    assert len([item for item in jobs if item["status"] == "RUNNING"]) == 0


def test_ver_f_trn_003_transitions_and_cancel(baseline_client: TestClient) -> None:
    """VER-F-TRN-003: 図の遷移のみ。QUEUED/RUNNING の中止。終端への中止は 409。"""
    _ready_baseline_set(baseline_client)
    running_job = baseline_client.post(
        "/api/jobs", json={"epochs": 8, "augmentation": False}
    )
    queued_job = baseline_client.post(
        "/api/jobs", json={"epochs": 1, "augmentation": False}
    )
    assert running_job.status_code == 201
    assert queued_job.status_code == 201
    observed: list[tuple[str, str]] = []
    deadline = time.monotonic() + 20
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        jobs = {item["ref"]: item["status"] for item in _state(baseline_client)["jobs"]}
        for ref, status in jobs.items():
            if last.get(ref) != status:
                observed.append((ref, status))
                previous = last.get(ref)
                if previous is not None:
                    assert status in ALLOWED_TRANSITIONS[previous]
                last[ref] = status
        queued_ref = queued_job.json()["ref"]
        if queued_ref in jobs and jobs[queued_ref] == "QUEUED":
            break
        time.sleep(0.05)
    queued_ref = queued_job.json()["ref"]
    cancel_queued = baseline_client.post(f"/api/jobs/{queued_ref}/cancel")
    assert cancel_queued.status_code == 200
    queued_done = wait_job(baseline_client, queued_ref, timeout=10)
    assert queued_done["status"] == "CANCELED"
    assert queued_done["model_ref"] is None

    running_ref = running_job.json()["ref"]
    started = time.monotonic()
    cancel_running = baseline_client.post(f"/api/jobs/{running_ref}/cancel")
    assert cancel_running.status_code == 200
    running_done = wait_job(baseline_client, running_ref, timeout=10)
    assert time.monotonic() - started <= 10
    assert running_done["status"] == "CANCELED"
    assert running_done["model_ref"] is None

    terminal = baseline_client.post(f"/api/jobs/{running_ref}/cancel")
    assert terminal.status_code == 409
    assert terminal.json()["code"] == "job_not_cancelable"


def test_ver_f_trn_004_epoch_progress_and_logs(baseline_client: TestClient) -> None:
    """VER-F-TRN-004: current_epoch が単調増加し、完了前にログが増える。"""
    _ready_baseline_set(baseline_client)
    created = baseline_client.post(
        "/api/jobs", json={"epochs": 3, "augmentation": False}
    )
    ref = created.json()["ref"]
    epochs_seen: list[int] = []
    logs_before_done = 0
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        job = baseline_client.get(f"/api/jobs/{ref}").json()
        epochs_seen.append(int(job["current_epoch"]))
        logs = baseline_client.get(f"/api/jobs/{ref}/logs").json()
        if job["status"] != "SUCCEEDED":
            logs_before_done = max(logs_before_done, logs["total"])
        if job["status"] in TERMINAL:
            break
        time.sleep(0.05)
    finished = wait_job(baseline_client, ref)
    assert finished["status"] == "SUCCEEDED"
    assert epochs_seen == sorted(epochs_seen)
    assert max(epochs_seen) >= 3
    assert logs_before_done >= 1
    logs = baseline_client.get(f"/api/jobs/{ref}/logs").json()
    assert logs["total"] >= 3
    assert [item["epoch"] for item in logs["items"]] == [1, 2, 3]
    for item in logs["items"]:
        assert "train_loss" in item
        assert "val_loss" in item
        assert "val_accuracy" in item
        assert "duration_seconds" in item


def test_ver_f_trn_005_baseline_paths_and_thirty_images(
    baseline_client: TestClient,
) -> None:
    """VER-F-TRN-005: ベースラインあり/なしが成功。30 枚ではなしは拒否。"""
    _ready_baseline_set(baseline_client, train_a=15, train_b=14, val=1, test=0)
    with_baseline = baseline_client.post(
        "/api/jobs", json={"epochs": 1, "augmentation": False, "use_baseline": True}
    )
    assert with_baseline.status_code == 201
    with_done = wait_job(baseline_client, with_baseline.json()["ref"])
    assert with_done["status"] == "SUCCEEDED"

    refused = baseline_client.post(
        "/api/jobs", json={"epochs": 1, "use_baseline": False}
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "training_precondition"

    _plant(
        baseline_client,
        class_id="samoyed",
        split="train",
        count=20,
        color=(180, 180, 180),
        salt0=200,
    )
    _plant(
        baseline_client,
        class_id="boxer",
        split="train",
        count=20,
        color=(30, 10, 10),
        salt0=240,
    )
    without = baseline_client.post(
        "/api/jobs",
        json={"epochs": 1, "augmentation": False, "use_baseline": False},
    )
    assert without.status_code == 201
    done = wait_job(baseline_client, without.json()["ref"], timeout=180)
    assert done["status"] == "SUCCEEDED"


def test_ver_f_trn_006_reproducible_test_accuracy(
    baseline_client: TestClient,
) -> None:
    """VER-F-TRN-006: 同一条件の試験正解率差は 0.02 以内。"""
    _ready_baseline_set(baseline_client)
    params = {
        "epochs": 2,
        "batch_size": 8,
        "learning_rate": 0.01,
        "seed": 42,
        "augmentation": False,
        "use_baseline": True,
    }
    first = baseline_client.post("/api/jobs", json=params)
    first_done = wait_job(baseline_client, first.json()["ref"])
    second = baseline_client.post("/api/jobs", json=params)
    second_done = wait_job(baseline_client, second.json()["ref"])
    assert first_done["status"] == "SUCCEEDED"
    assert second_done["status"] == "SUCCEEDED"
    models = {item["ref"]: item for item in _state(baseline_client)["models"]}
    acc1 = float(models[first_done["model_ref"]]["metrics"]["accuracy"])
    acc2 = float(models[second_done["model_ref"]]["metrics"]["accuracy"])
    assert abs(acc1 - acc2) <= 0.02


def test_ver_f_trn_007_restart_fails_running(tmp_path: Path) -> None:
    """VER-F-TRN-007: 再起動後に残存 RUNNING は FAILED。不変条件も成立。"""
    settings = _settings(tmp_path, REPO_ASSETS)
    with TestClient(create_app(settings)) as client:
        _ready_baseline_set(client)
        client.get("/api/_state")
    db = settings.data_dir / DB_FILENAME
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO jobs (ref, status, current_epoch, total_epochs, created_at)
        VALUES (?, 'RUNNING', 2, 10, ?)
        """,
        ("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "2026-09-13T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    with TestClient(create_app(settings)) as client:
        jobs = _state(client)["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["status"] == "FAILED"
        assert jobs[0]["failed"] is True
        models = _state(client)["models"]
        actives = [item for item in models if item["active"]]
        assert len(actives) <= 1
        versions = [item["version"] for item in models]
        assert versions.count(0) <= 1
        assert len([item for item in jobs if item["status"] == "RUNNING"]) == 0


def test_ver_f_mdl_002_first_trained_activates_second_does_not(
    baseline_client: TestClient,
) -> None:
    """最初の学習済で active が版 1 へ。2 件目では切り替わらない。"""
    _ready_baseline_set(baseline_client)
    models = _state(baseline_client)["models"]
    assert models[0]["version"] == 0
    assert models[0]["active"] is True
    first = wait_job(
        baseline_client,
        baseline_client.post(
            "/api/jobs", json={"epochs": 1, "augmentation": False}
        ).json()["ref"],
    )
    assert first["status"] == "SUCCEEDED"
    models = {item["version"]: item for item in _state(baseline_client)["models"]}
    assert models[1]["active"] is True
    assert models[0]["active"] is False
    second = wait_job(
        baseline_client,
        baseline_client.post(
            "/api/jobs", json={"epochs": 1, "augmentation": False}
        ).json()["ref"],
    )
    assert second["status"] == "SUCCEEDED"
    models = {item["version"]: item for item in _state(baseline_client)["models"]}
    assert models[1]["active"] is True
    assert models[2]["active"] is False


def test_missing_job_is_404(baseline_client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000099"
    response = baseline_client.get(f"/api/jobs/{missing}")
    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"
    logs = baseline_client.get(f"/api/jobs/{missing}/logs")
    assert logs.status_code == 404


def test_baseline_unavailable_when_assets_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tmp_path / "missing-assets")
    with TestClient(create_app(settings)) as client:
        _plant(client, class_id="samoyed", split="train", count=6, color=(1, 2, 3))
        _plant(
            client,
            class_id="boxer",
            split="train",
            count=6,
            color=(4, 5, 6),
            salt0=10,
        )
        _plant(
            client,
            class_id="samoyed",
            split="val",
            count=1,
            color=(7, 8, 9),
            salt0=20,
        )
        response = client.post("/api/jobs", json={"use_baseline": True})
        assert response.status_code == 422
        assert response.json()["code"] == "baseline_unavailable"


def test_defaults_applied_when_body_omitted(baseline_client: TestClient) -> None:
    _ready_baseline_set(baseline_client)
    response = baseline_client.post("/api/jobs")
    assert response.status_code == 201
    row = _app_store(baseline_client).get_job(response.json()["ref"])
    assert row is not None
    assert row.params["epochs"] == 10
    assert row.params["batch_size"] == 32
    assert row.params["learning_rate"] == 0.001
    assert row.params["seed"] == 42
    assert row.params["augmentation"] is True
    assert row.params["use_baseline"] is True
    baseline_client.post(f"/api/jobs/{response.json()['ref']}/cancel")
    wait_job(baseline_client, response.json()["ref"], timeout=15)


def test_suggestions_are_not_counted(baseline_client: TestClient) -> None:
    _plant(
        baseline_client,
        class_id="samoyed",
        split="train",
        count=5,
        color=(1, 1, 1),
    )
    _plant(
        baseline_client,
        class_id="boxer",
        split="train",
        count=4,
        color=(2, 2, 2),
        salt0=8,
    )
    _plant(
        baseline_client,
        class_id="samoyed",
        split="val",
        count=1,
        color=(3, 3, 3),
        salt0=16,
    )
    response = baseline_client.post("/api/jobs", json={"epochs": 1})
    assert response.status_code == 422


def test_chance_level_beaten_on_baseline_head(baseline_client: TestClient) -> None:
    """REQ-CON-008: 少なくとも 1 条件で偶然水準 0.125 を上回る。"""
    _ready_baseline_set(baseline_client, train_a=8, train_b=8, val=2, test=4)
    done = wait_job(
        baseline_client,
        baseline_client.post(
            "/api/jobs",
            json={
                "epochs": 5,
                "batch_size": 8,
                "learning_rate": 0.05,
                "augmentation": False,
            },
        ).json()["ref"],
    )
    assert done["status"] == "SUCCEEDED"
    model = next(
        item
        for item in _state(baseline_client)["models"]
        if item["ref"] == done["model_ref"]
    )
    assert model["metrics"] is not None
    assert float(model["metrics"]["accuracy"]) > 0.125


def test_api_process_does_not_import_torch(tmp_path: Path) -> None:
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from fastapi.testclient import TestClient
        from faunalab.api.app import create_app
        from faunalab.settings import Settings
        settings = Settings(
            data_dir=Path({str(tmp_path / "data")!r}),
            assets_dir=Path({str(tmp_path / "missing")!r}),
            web_dist_dir=Path("/missing-dist"),
        )
        with TestClient(create_app(settings)) as client:
            client.get("/api/_state")
        assert "torch" not in sys.modules
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_job_create_rejects_out_of_range_params() -> None:
    with pytest.raises(ValidationError):
        JobCreateRequest(epochs=1001)
    with pytest.raises(ValidationError):
        JobCreateRequest(batch_size=513)
    with pytest.raises(ValidationError):
        JobCreateRequest(learning_rate=float("inf"))
    with pytest.raises(ValidationError):
        JobCreateRequest(learning_rate=float("nan"))
    with pytest.raises(ValidationError):
        JobCreateRequest(learning_rate=0)


def test_job_create_http_rejects_too_many_epochs(
    baseline_client: TestClient,
) -> None:
    response = baseline_client.post("/api/jobs", json={"epochs": 1001})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_complete_training_writes_onnx_before_row(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    store.initialize()
    store.insert_job(
        ref="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1",
        total_epochs=1,
        params_json=JobParams(epochs=1).to_json(),
        created_at="2026-09-13T00:00:00Z",
    )
    claimed = store.claim_next_queued()
    assert claimed is not None
    payload = b"onnx-artifact"
    outcome = store.complete_training_success(
        claimed.ref,
        artifact_bytes=payload,
        metrics=None,
        created_at="2026-09-13T00:00:01Z",
    )
    assert outcome == "succeeded"
    finished = store.get_job(claimed.ref)
    assert finished is not None
    assert finished.status == "SUCCEEDED"
    assert finished.model_ref is not None
    model = store.get_model(finished.model_ref)
    assert model is not None
    onnx_path = store.data_dir / (model.artifact_dir or "models/1") / TRAINED_ONNX_NAME
    assert onnx_path.read_bytes() == payload
    store.close()


def test_complete_training_honors_cancel(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    store.initialize()
    store.insert_job(
        ref="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee2",
        total_epochs=1,
        params_json=JobParams(epochs=1).to_json(),
        created_at="2026-09-13T00:00:00Z",
    )
    claimed = store.claim_next_queued()
    assert claimed is not None
    store.request_cancel(claimed.ref)
    before = [row.ref for row in store.list_models()]
    outcome = store.complete_training_success(
        claimed.ref,
        artifact_bytes=b"should-not-write",
        metrics=None,
        created_at="2026-09-13T00:00:01Z",
    )
    assert outcome == "canceled"
    finished = store.get_job(claimed.ref)
    assert finished is not None
    assert finished.status == "CANCELED"
    assert finished.model_ref is None
    assert [row.ref for row in store.list_models()] == before
    store.close()


def test_supervisor_restarts_exited_child(tmp_path: Path) -> None:
    marker = tmp_path / "runs"
    script = (
        "import pathlib, time\n"
        f"p = pathlib.Path({str(marker)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\n"
        "p.write_text(str(n + 1))\n"
        "if n == 0:\n"
        "    raise SystemExit(0)\n"
        "time.sleep(30)\n"
    )
    handle = start_worker(
        tmp_path,
        tmp_path,
        argv=[sys.executable, "-c", script],
        poll_seconds=0.1,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if marker.exists() and int(marker.read_text()) >= 2:
                break
            time.sleep(0.05)
        assert int(marker.read_text()) >= 2
    finally:
        stop_worker(handle)
