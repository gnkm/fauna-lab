"""SPA fallback so UI paths survive reload (REQ-UI-002)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.settings import Settings


def test_spa_unknown_path_returns_index(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><title>FaunaLab</title><div id='root'>ui</div>",
        encoding="utf-8",
    )
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings = Settings(
        web_dist_dir=dist,
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "missing-assets",
    )
    with TestClient(create_app(settings)) as client:
        index = client.get("/")
        nested = client.get("/images")
        detail = client.get("/images/abc")
        script = client.get("/assets/app.js")
        stats = client.get("/api/stats")
        missing_api = client.get("/api/does-not-exist")
    assert index.status_code == 200
    assert "FaunaLab" in index.text
    assert nested.status_code == 200
    assert "FaunaLab" in nested.text
    assert detail.status_code == 200
    assert "FaunaLab" in detail.text
    assert script.status_code == 200
    assert "console.log" in script.text
    assert stats.status_code == 200
    assert stats.json()["image_count"] == 0
    assert missing_api.status_code == 404
    assert "text/html" not in missing_api.headers.get("content-type", "")

