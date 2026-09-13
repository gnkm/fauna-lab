"""Parse assets/sample/manifest.json (REQ-F-SYS-003)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from faunalab.domain.classes import CLASS_IDS


class SampleUnavailableError(Exception):
    """Sample assets are missing or unreadable."""


class SampleManifestError(ValueError):
    """manifest.json exists but its contents are not usable."""


@dataclass(frozen=True, slots=True)
class SampleItem:
    file: str
    class_id: str
    path: Path


def sample_dir(assets_dir: Path) -> Path:
    return assets_dir / "sample"


def sample_manifest_path(assets_dir: Path) -> Path:
    return sample_dir(assets_dir) / "manifest.json"


def load_sample_items(assets_dir: Path) -> list[SampleItem]:
    manifest = sample_manifest_path(assets_dir)
    if not manifest.is_file():
        raise SampleUnavailableError("assets/sample/manifest.json がありません。")
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SampleUnavailableError("sample のマニフェストを読めません。") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise SampleManifestError("manifest.json の items が不正です。")
    root = sample_dir(assets_dir).resolve()
    items: list[SampleItem] = []
    for entry in raw["items"]:
        if not isinstance(entry, dict):
            raise SampleManifestError("manifest.json の要素が不正です。")
        file = entry.get("file")
        class_id = entry.get("class_id")
        if not isinstance(file, str) or not file:
            raise SampleManifestError("manifest.json の file が不正です。")
        if class_id not in CLASS_IDS:
            raise SampleManifestError("manifest.json の class_id が不正です。")
        relative = Path(file)
        if relative.is_absolute() or ".." in relative.parts:
            raise SampleManifestError("manifest.json のパスが不正です。")
        path = (sample_dir(assets_dir) / relative).resolve()
        if not path.is_relative_to(root):
            raise SampleManifestError("manifest.json のパスが不正です。")
        if not path.is_file():
            raise SampleUnavailableError(f"サンプル画像がありません: {file}")
        items.append(SampleItem(file=file, class_id=str(class_id), path=path))
    return items
