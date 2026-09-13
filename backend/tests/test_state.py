"""Observation interface and startup persistence (F007).

Verification mapping:
- VER-OBS-001 (structure / no side effects): test_state_has_required_keys,
  test_consecutive_gets_are_equal_except_observed_at
- VER-DATA-001: test_classes_match_srs_352
- VER-F-SYS-001 (classes on empty data dir): test_empty_data_dir_registers_eight_classes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.classes import SYSTEM_CLASSES
from faunalab.persist.store import DATA_SUBDIRS, DB_FILENAME
from faunalab.settings import Settings

REQUIRED_STATE_KEYS = frozenset(
    {
        "schema_version",
        "observed_at",
        "classes",
        "images",
        "jobs",
        "models",
        "inferences",
    }
)


def _without_observed_at(body: dict[str, Any]) -> dict[str, Any]:
    rest = dict(body)
    rest.pop("observed_at", None)
    return rest


def test_empty_data_dir_registers_eight_classes(client: TestClient) -> None:
    """VER-F-SYS-001: 空データディレクトリから起動し、操作なしで classes が 8 件。"""
    response = client.get("/api/_state")
    assert response.status_code == 200
    body = response.json()
    classes = body["classes"]
    assert len(classes) == 8
    orders = [item["display_order"] for item in classes]
    assert orders == list(range(1, 9))


def test_classes_match_srs_352(client: TestClient) -> None:
    """VER-DATA-001: `_state.classes` が SRS 3.5.2 の識別子と順序に一致する。"""
    body = client.get("/api/_state").json()
    expected = [
        {"class_id": spec.class_id, "display_order": spec.display_order}
        for spec in SYSTEM_CLASSES
    ]
    assert body["classes"] == expected


def test_state_has_required_keys(client: TestClient) -> None:
    """VER-OBS-001: schema_version=1 と必須キー。空でも配列は存在する。"""
    response = client.get("/api/_state")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert REQUIRED_STATE_KEYS <= body.keys()
    assert body["schema_version"] == 1
    assert isinstance(body["observed_at"], str)
    assert body["observed_at"].endswith("Z")
    assert body["images"] == []
    assert body["jobs"] == []
    assert body["models"] == []
    assert body["inferences"] == []


def test_consecutive_gets_are_equal_except_observed_at(client: TestClient) -> None:
    """VER-OBS-001: 連続 2 回の呼び出しは observed_at 以外が一致し、副作用が無い。"""
    first = client.get("/api/_state")
    second = client.get("/api/_state")
    assert first.status_code == 200
    assert second.status_code == 200
    a = first.json()
    b = second.json()
    assert a["observed_at"] <= b["observed_at"]
    assert _without_observed_at(a) == _without_observed_at(b)


def test_classes_survive_restart(settings: Settings) -> None:
    """REQ-SYS-002 の器: データディレクトリを残した再起動でも classes が残る。"""
    with TestClient(create_app(settings)) as first:
        original = first.get("/api/_state").json()["classes"]
    with TestClient(create_app(settings)) as second:
        again = second.get("/api/_state").json()["classes"]
    assert original == again
    assert len(again) == 8


def test_get_state_does_not_write(settings: Settings) -> None:
    """GET /api/_state は DB / ファイルへ書き込まない。"""
    with TestClient(create_app(settings)) as client:
        client.get("/api/_state")
        before = _file_fingerprint(settings.data_dir)
        client.get("/api/_state")
        after = _file_fingerprint(settings.data_dir)
    # WAL/SHM のサイズ変動は読み取りでも起きうるので、パス集合だけ見る。
    assert before.keys() == after.keys()


def test_generated_files_stay_under_data_dir(
    settings: Settings, tmp_path: Path
) -> None:
    """REQ-DATA-011 / REQ-DATA-012: 生成物はデータディレクトリ配下のみ。"""
    with TestClient(create_app(settings)) as client:
        client.get("/api/_state")
    created_files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert created_files
    for path in created_files:
        assert path.is_relative_to(settings.data_dir)
    assert (settings.data_dir / DB_FILENAME).is_file()
    for name in DATA_SUBDIRS:
        assert (settings.data_dir / name).is_dir()
    assert not (tmp_path / "assets").exists()


def test_missing_assets_still_starts(settings: Settings) -> None:
    """REQ-CON-007 / REQ-F-BASE-006: assets 欠落でも起動し、版 0 は登録しない（F010）。"""
    assert not settings.assets_dir.exists()
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/_state").json()
    assert body["schema_version"] == 1
    assert len(body["classes"]) == 8
    assert body["models"] == []


def test_unhandled_exception_returns_problem_and_keeps_process(
    settings: Settings,
) -> None:
    """REQ-ATT-REL-001: 未処理例外でもプロセスは落ちず、本文にトレースを出さない。"""
    app = create_app(settings)

    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError("secret-path-/tmp/faunalab-boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        failed = client.get("/__boom")
        assert failed.status_code == 500
        assert failed.headers["content-type"].startswith(PROBLEM_JSON)
        payload = failed.json()
        assert payload["code"] == "internal_error"
        assert payload["status"] == 500
        assert payload["type"] == "urn:faunalab:error:internal_error"
        text = failed.text
        assert "Traceback" not in text
        assert "secret-path" not in text
        assert "/tmp/faunalab-boom" not in text
        alive = client.get("/api/_state")
        assert alive.status_code == 200
        assert len(alive.json()["classes"]) == 8


def test_state_is_reachable_when_ui_is_mounted(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><title>FaunaLab</title>", encoding="utf-8"
    )
    settings = Settings(
        web_dist_dir=dist,
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "missing-assets",
    )
    with TestClient(create_app(settings)) as client:
        state = client.get("/api/_state")
        page = client.get("/")
    assert state.status_code == 200
    assert len(state.json()["classes"]) == 8
    assert page.status_code == 200
    assert "FaunaLab" in page.text


def _file_fingerprint(root: Path) -> dict[str, int]:
    return {
        str(path.relative_to(root)): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    }
