"""ASGI application skeleton."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.settings import Settings


def test_openapi_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "FaunaLab"


def test_swagger_html_is_disabled(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 404


def test_cors_middleware_is_added_when_origins_set(tmp_path: Path) -> None:
    settings = Settings(
        cors_origins="http://localhost:5173",
        web_dist_dir=Path("/missing-dist"),
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "assets",
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/openapi.json",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )


def test_static_index_is_mounted(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><title>FaunaLab</title>", encoding="utf-8"
    )
    settings = Settings(
        web_dist_dir=dist,
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "assets",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "FaunaLab" in response.text
