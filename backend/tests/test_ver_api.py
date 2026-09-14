"""VER-API-001: OpenAPI との一致、7 類ステータス、本文にパス/トレースを含めない。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.images import MAX_IMAGE_BYTES
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
