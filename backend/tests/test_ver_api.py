"""VER-API-001: OpenAPI との一致、7 類ステータス、本文にパス/トレースを含めない。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import ERROR_STATUS, PROBLEM_JSON
from faunalab.domain.images import MAX_IMAGE_BYTES
from faunalab.domain.jobs import TERMINAL_STATUSES
from faunalab.settings import Settings, get_settings
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "openapi.yaml"
MISSING_REF = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
FORBIDDEN_LEAKS = (
    "Traceback",
    "traceback",
    "File \"",
    ".py\", line",
    "SELECT ",
    "/tmp/",
    "/workspace",
    "/var/lib/faunalab",
    "secret-path",
)


def _jpeg(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    image = Image.new("RGB", (16, 16), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _oversize_jpeg() -> bytes:
    small = _jpeg()
    pad = MAX_IMAGE_BYTES + 1 - len(small)
    return small + (b"\x00" * max(pad, 1))


def _problem_has_no_leaks(response: Any) -> None:
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    text = response.text
    for token in FORBIDDEN_LEAKS:
        assert token not in text
        assert token not in str(body.get("detail", ""))
    assert "type" in body and "code" in body and "detail" in body


def test_ver_api_001_openapi_paths_match_implementation(client: TestClient) -> None:
    """VER-API-001: 提出 OpenAPI の path+method が実行時 `/openapi.json` と一致する。"""

    yaml = pytest.importorskip("yaml")
    documented = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    live = client.get("/openapi.json").json()
    documented_ops: set[tuple[str, str]] = set()
    for path, item in documented["paths"].items():
        for method, spec in item.items():
            if method.startswith("x-") or not isinstance(spec, dict):
                continue
            documented_ops.add((path, method.lower()))
    live_ops: set[tuple[str, str]] = set()
    for path, item in live["paths"].items():
        for method, spec in item.items():
            if method.startswith("x-") or not isinstance(spec, dict):
                continue
            live_ops.add((path, method.lower()))
    missing = documented_ops - live_ops
    extra = {
        op for op in live_ops if op[0].startswith("/api/")
    } - documented_ops
    assert missing == set(), f"documented but missing from implementation: {missing}"
    assert extra == set(), f"implementation /api paths not in openapi.yaml: {extra}"


def test_ver_api_001_seven_statuses_are_distinct(settings: Settings) -> None:
    """VER-API-001: REQ-API-003 の 7 状況が異なるステータスで返る。"""

    app = create_app(settings)

    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError("secret-path-/tmp/faunalab-boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        bad_json = client.get("/api/images", params={"limit": 0})
        missing = client.get(f"/api/images/{MISSING_REF}")
        payload = _jpeg(color=(1, 2, 3))
        first = client.post(
            "/api/images",
            files=[("files", ("a.jpg", payload, "image/jpeg"))],
        )
        assert first.status_code == 200
        duplicate = client.post(
            "/api/images",
            files=[("files", ("b.jpg", payload, "image/jpeg"))],
        )
        no_model = client.post(
            "/api/inferences",
            files=[("files", ("c.jpg", _jpeg(color=(4, 5, 6)), "image/jpeg"))],
        )
        fake = client.post(
            "/api/images",
            files=[("files", ("d.jpg", b"not-an-image", "image/jpeg"))],
        )
        oversize = client.post(
            "/api/images",
            files=[("files", ("e.jpg", _oversize_jpeg(), "image/jpeg"))],
        )
        internal = client.get("/__boom")

        by_status = {
            400: bad_json,
            404: missing,
            409: duplicate,
            422: no_model,
            415: fake,
            413: oversize,
            500: internal,
        }
        assert set(by_status) == {400, 404, 409, 413, 415, 422, 500}
        codes = {
            400: "validation_error",
            404: "image_not_found",
            409: "image_duplicate",
            422: "no_active_model",
            415: "unsupported_media_type",
            413: "payload_too_large",
            500: "internal_error",
        }
        for status, response in by_status.items():
            assert response.status_code == status, response.text
            _problem_has_no_leaks(response)
            body = response.json()
            assert body["status"] == status
            assert body["code"] == codes[status]
            assert body["type"] == f"urn:faunalab:error:{codes[status]}"
        alive = client.get("/api/_state")
        assert alive.status_code == 200
    get_settings.cache_clear()


def test_ver_api_001_error_bodies_omit_paths(
    settings: Settings,
) -> None:
    """VER-API-001: 意図的例外の本文にパスとスタックトレースが無い。"""

    app = create_app(settings)

    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError("secret-path-/tmp/faunalab-boom")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/__boom")
        assert response.status_code == 500
        _problem_has_no_leaks(response)
        assert test_client.get("/api/_state").status_code == 200


def _documented_ops() -> set[tuple[str, str]]:
    yaml = pytest.importorskip("yaml")
    documented = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    ops: set[tuple[str, str]] = set()
    for path, item in documented["paths"].items():
        for method, spec in item.items():
            if method.startswith("x-") or not isinstance(spec, dict):
                continue
            ops.add((path, method.lower()))
    return ops


def _jpeg_named(color: tuple[int, int, int], name: str) -> tuple[str, bytes, str]:
    return (name, _jpeg(color), "image/jpeg")


def test_ver_api_001_all_documented_operations_are_invoked(
    tmp_path: Path,
) -> None:
    """VER-API-001: 提出 OpenAPI に記載したすべての操作を呼び出す。"""

    settings = Settings(
        data_dir=tmp_path / "data",
        assets_dir=REPO_ROOT / "assets",
        web_dist_dir=tmp_path / "missing-dist",
    )
    get_settings.cache_clear()
    invoked: set[tuple[str, str]] = set()
    with TestClient(create_app(settings)) as client:
        def mark(path: str, method: str) -> None:
            invoked.add((path, method))

        assert client.get("/api/_state").status_code == 200
        mark("/api/_state", "get")
        assert client.get("/api/stats").status_code == 200
        mark("/api/stats", "get")
        assert client.get("/api/images").status_code == 200
        mark("/api/images", "get")
        assert client.get("/api/jobs").status_code == 200
        mark("/api/jobs", "get")
        assert client.get("/api/models").status_code == 200
        mark("/api/models", "get")
        assert client.get("/api/inferences").status_code == 200
        mark("/api/inferences", "get")
        assert client.get("/api/suggestions").status_code == 200
        mark("/api/suggestions", "get")

        queued = client.post("/api/jobs", json={})
        assert queued.status_code in {201, 422}
        mark("/api/jobs", "post")
        missing_job = client.get(f"/api/jobs/{MISSING_REF}")
        assert missing_job.status_code == 404
        mark("/api/jobs/{ref}", "get")
        logs = client.get(f"/api/jobs/{MISSING_REF}/logs")
        assert logs.status_code == 404
        mark("/api/jobs/{ref}/logs", "get")
        cancel = client.post(f"/api/jobs/{MISSING_REF}/cancel")
        assert cancel.status_code == 404
        mark("/api/jobs/{ref}/cancel", "post")

        models = client.get("/api/models").json()["items"]
        v0 = next(item for item in models if item["version"] == 0)
        assert "created_at" in v0
        assert client.get(f"/api/models/{v0['ref']}").status_code == 200
        mark("/api/models/{ref}", "get")
        activated = client.post(f"/api/models/{v0['ref']}/activate")
        assert activated.status_code == 200
        mark("/api/models/{ref}/activate", "post")
        evaluated = client.post(f"/api/models/{v0['ref']}/evaluate")
        assert evaluated.status_code in {200, 422}
        mark("/api/models/{ref}/evaluate", "post")
        refused = client.delete(f"/api/models/{v0['ref']}")
        assert refused.status_code == 409
        mark("/api/models/{ref}", "delete")

        uploaded = client.post(
            "/api/images",
            files=[("files", _jpeg_named((11, 22, 33), "one.jpg"))],
        )
        assert uploaded.status_code == 200
        mark("/api/images", "post")
        image_ref = uploaded.json()["items"][0]["ref"]
        detail = client.get(f"/api/images/{image_ref}")
        assert detail.status_code == 200
        assert "original_name" in detail.json()
        mark("/api/images/{ref}", "get")
        thumb = client.get(f"/api/images/{image_ref}/thumbnail")
        assert thumb.status_code == 200
        mark("/api/images/{ref}/thumbnail", "get")
        labeled = client.put(
            f"/api/images/{image_ref}/label",
            json={"class_id": "samoyed", "source": "human"},
        )
        assert labeled.status_code == 200
        mark("/api/images/{ref}/label", "put")
        bulk = client.post(
            "/api/labels/bulk",
            json={"refs": [image_ref], "class_id": "boxer"},
        )
        assert bulk.status_code == 200
        mark("/api/labels/bulk", "post")
        unlabeled = client.delete(f"/api/images/{image_ref}/label")
        assert unlabeled.status_code == 204
        mark("/api/images/{ref}/label", "delete")

        inferred = client.post(
            "/api/inferences",
            json={"refs": [image_ref]},
        )
        assert inferred.status_code == 200
        mark("/api/inferences", "post")
        generated = client.post("/api/suggestions", json={})
        assert generated.status_code == 200
        mark("/api/suggestions", "post")
        accepted = client.post(
            "/api/suggestions/accept",
            json={"refs": [image_ref]},
        )
        assert accepted.status_code in {200, 404}
        mark("/api/suggestions/accept", "post")
        threshold = client.post(
            "/api/suggestions/accept-by-threshold",
            json={"min_confidence": 0.99},
        )
        assert threshold.status_code == 200
        mark("/api/suggestions/accept-by-threshold", "post")
        rejected = client.post(
            "/api/suggestions/reject",
            json={"refs": [image_ref]},
        )
        assert rejected.status_code in {200, 404}
        mark("/api/suggestions/reject", "post")

        imported = client.post("/api/sample/import")
        assert imported.status_code in {200, 422}
        mark("/api/sample/import", "post")
        split = client.post("/api/splits", json={})
        assert split.status_code == 200
        mark("/api/splits", "post")

        state = client.get("/api/_state").json()
        for model in state["models"]:
            assert "created_at" not in model
        deleted = client.delete(f"/api/images/{image_ref}")
        assert deleted.status_code == 204
        mark("/api/images/{ref}", "delete")

    get_settings.cache_clear()
    missing = _documented_ops() - invoked
    assert missing == set(), f"documented ops not invoked: {sorted(missing)}"


def test_ver_api_001_error_codes_and_job_statuses_match_design() -> None:
    """VER-API-001: DESIGN の誤り ID とジョブ状態がコードと OpenAPI にある。"""

    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    enum_codes = doc["components"]["schemas"]["ErrorCode"]["enum"]
    assert set(enum_codes) == set(ERROR_STATUS)
    design = (REPO_ROOT / "DESIGN.md").read_text(encoding="utf-8")
    for code in ERROR_STATUS:
        assert f"`{code}`" in design, code
    statuses = doc["components"]["schemas"]["JobStatus"]["enum"]
    assert set(statuses) == {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"}
    assert TERMINAL_STATUSES == frozenset({"SUCCEEDED", "FAILED", "CANCELED"})
    for status in statuses:
        assert status in design
