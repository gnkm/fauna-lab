"""VER-CON-001 / VER-CON-002: ネット遮断の代替と環境変数。"""

from __future__ import annotations

from pathlib import Path

import pytest
from faunalab.settings import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ver_con_001_compose_blocks_runtime_pull() -> None:
    """VER-CON-001: 実行時 pull 禁止と NAT 出口抑制。完全エアギャップは提出時。"""

    text = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "pull_policy: never" in text
    assert "com.docker.network.bridge.enable_ip_masquerade: \"false\"" in text
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "podman compose up --pull never" in readme
    assert "--build" in readme
    assert "実行コマンドに含めない" in readme


def test_ver_con_002_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VER-CON-002: 待受・ディレクトリ・CORS・閾値が環境変数から入る。"""

    data_dir = tmp_path / "custom-data"
    assets_dir = tmp_path / "custom-assets"
    monkeypatch.setenv("FAUNALAB_PORT", "8123")
    monkeypatch.setenv("FAUNALAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("FAUNALAB_ASSETS_DIR", str(assets_dir))
    monkeypatch.setenv("FAUNALAB_CORS_ORIGINS", "http://example.invalid")
    monkeypatch.setenv("FAUNALAB_CONFIDENCE_THRESHOLD", "0.9")
    monkeypatch.setenv("FAUNALAB_OTHER_MASS_THRESHOLD", "0.8")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.port == 8123
    assert settings.data_dir == data_dir
    assert settings.assets_dir == assets_dir
    assert settings.cors_origin_list() == ["http://example.invalid"]
    assert settings.confidence_threshold == 0.9
    assert settings.other_mass_threshold == 0.8
    get_settings.cache_clear()
