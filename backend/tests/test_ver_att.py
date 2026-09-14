"""VER-ATT-001〜004: 信頼性・入力の扱い・保守性・複製。"""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.settings import Settings, get_settings
from PIL import Image

from tests.invariants import assert_observation_invariants, without_observed_at

REPO_ROOT = Path(__file__).resolve().parents[2]


def _jpeg(color: tuple[int, int, int] = (8, 9, 10), salt: int = 0) -> bytes:
    image = Image.new("RGB", (20, 16), color)
    image.putpixel((salt % 20, 1), (salt % 256, 2, 3))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _upload(client: TestClient, data: bytes, name: str) -> Any:
    return client.post(
        "/api/images", files=[("files", (name, data, "image/jpeg"))]
    )


def test_ver_att_001_malformed_requests_keep_process(client: TestClient) -> None:
    """VER-ATT-001: 不正要求が連続しても応答し、プロセスは生存する。"""

    cases = [
        client.put(
            "/api/images/not-a-uuid/label",
            json={"class_id": "samoyed"},
        ),
        client.put(
            "/api/images/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/label",
            json={"class_id": 1},
        ),
        client.post("/api/jobs", content=b"", headers={"content-type": "application/json"}),
        client.post(
            "/api/labels/bulk",
            json={"refs": ["x" * 8000], "class_id": "samoyed"},
        ),
        _upload(client, b"\xff\xd8\xff" + b"\x00" * 16, "truncated.jpg"),
    ]
    for response in cases:
        assert response.status_code >= 400
        assert response.status_code < 600
        assert response.headers.get("content-type", "").startswith(PROBLEM_JSON)
        assert "Traceback" not in response.text
    alive = client.get("/api/_state")
    assert alive.status_code == 200
    assert_observation_invariants(alive.json())
    ok = _upload(client, _jpeg((1, 2, 3), 4), "after.jpg")
    assert ok.status_code == 200
    assert ok.json()["items"][0]["ok"] is True


def test_ver_att_002_special_names_stay_values(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    """VER-ATT-002: パス横断・特殊文字・HTML タグのファイル名は値として保持する。"""

    names = [
        "../../../etc/passwd.jpg",
        "foo;rm -rf --no-preserve-root.jpg",
        "<img src=x onerror=alert(1)>.jpg",
        'quote"and\'tick.jpg',
    ]
    for index, name in enumerate(names):
        response = _upload(client, _jpeg((10, 20, index + 1), index + 2), name)
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["ok"] is True
        detail = client.get(f"/api/images/{item['ref']}")
        assert detail.status_code == 200
        assert detail.json()["original_name"] == name

    created = [p for p in tmp_path.rglob("*") if p.is_file()]
    for path in created:
        assert path.is_relative_to(settings.data_dir)
    image_dir = settings.data_dir / "images"
    stored = list(image_dir.iterdir())
    assert stored
    for path in stored:
        assert ".." not in path.name
        assert "<" not in path.name
        assert ";" not in path.name
        assert "passwd" not in path.name
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path.parent / "etc").exists()
    assert_observation_invariants(client.get("/api/_state").json())


def test_ver_att_003_readme_lint_and_single_command() -> None:
    """VER-ATT-003: 単一試験コマンド・静的解析設定・README 記載項目。"""

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "pnpm test" in readme
    assert "前提" in readme
    assert "起動" in readme
    assert "試験" in readme
    assert "サンプル" in readme
    assert "ARCHITECTURE.md" in readme or "DESIGN.md" in readme
    assert (REPO_ROOT / "biome.json").is_file()
    pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    assert "fail_under" in pyproject
    assert "70" in pyproject
    assert "[tool.ruff]" in pyproject
    assert "[tool.pyright]" in pyproject
    package = (REPO_ROOT / "package.json").read_text(encoding="utf-8")
    assert '"lint"' in package
    assert '"test"' in package
    matrix = (REPO_ROOT / "docs" / "verification-matrix.md").read_text(encoding="utf-8")
    assert "VER-OBS-001" in matrix
    assert "pnpm test" in matrix


def test_ver_att_004_copied_data_dir_restores_state(tmp_path: Path) -> None:
    """VER-ATT-004: データディレクトリ複製後の `_state` が一致する（縮小）。"""

    settings = Settings(
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "missing-assets",
        web_dist_dir=tmp_path / "missing-dist",
    )
    get_settings.cache_clear()
    with TestClient(create_app(settings)) as client:
        uploaded = _upload(client, _jpeg((11, 12, 13), 5), "keep.jpg")
        assert uploaded.status_code == 200
        ref = uploaded.json()["items"][0]["ref"]
        labeled = client.put(
            f"/api/images/{ref}/label",
            json={"class_id": "chihuahua", "source": "human"},
        )
        assert labeled.status_code == 200
        original = without_observed_at(client.get("/api/_state").json())
    replica = tmp_path / "replica"
    shutil.copytree(settings.data_dir, replica)
    copied = Settings(
        data_dir=replica,
        assets_dir=tmp_path / "missing-assets",
        web_dist_dir=tmp_path / "missing-dist",
    )
    get_settings.cache_clear()
    with TestClient(create_app(copied)) as client:
        restored = without_observed_at(client.get("/api/_state").json())
    assert restored == original
    assert restored["images"][0]["label"]["class_id"] == "chihuahua"
    assert_observation_invariants({"observed_at": "x", **restored})
    get_settings.cache_clear()
