"""Write and delete files only under the data directory (REQ-DATA-011)."""

from __future__ import annotations

import os
from pathlib import Path

_FILE_MODE = 0o644  # 実行ビットを付けない（REQ-ATT-SEC-002）


def resolve_under(root: Path, relative: str) -> Path:
    """相対パスを root 配下に解決する。横断したら ValueError。"""
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("path escapes data directory")
    root_resolved = root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ValueError("path escapes data directory")
    return candidate


def write_bytes(root: Path, relative: str, data: bytes) -> Path:
    path = resolve_under(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, _FILE_MODE)
    tmp.replace(path)
    os.chmod(path, _FILE_MODE)
    return path


def remove_if_present(root: Path, relative: str) -> None:
    path = resolve_under(root, relative)
    if path.is_file():
        path.unlink()
