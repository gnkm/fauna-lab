"""Baseline asset inspection and model version 0 registration (F010)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faunalab.domain.classes import CLASS_IDS
from faunalab.ml.fold import IMAGENET_CLASS_COUNT
from faunalab.persist.store import Store

LOGGER = logging.getLogger("faunalab.ml.baseline")

MANIFEST_NAME = "MANIFEST.json"
CLASS_MAP_NAME = "class_map.json"
BASELINE_SUBDIR = "baseline"
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class BaselineInspection:
    ok: bool
    reason: str
    class_map: dict[str, tuple[int, ...]] | None = None
    model_path: Path | None = None
    manifest: dict[str, Any] | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def inspect_baseline_assets(assets_dir: Path) -> BaselineInspection:
    """Validate MANIFEST hashes and class_map (REQ-F-BASE-005). Read-only."""

    if not assets_dir.is_dir():
        return BaselineInspection(ok=False, reason="assets directory missing")
    baseline_dir = assets_dir / BASELINE_SUBDIR
    if not baseline_dir.is_dir():
        return BaselineInspection(ok=False, reason="baseline directory missing")
    manifest_path = baseline_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return BaselineInspection(ok=False, reason="MANIFEST.json missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return BaselineInspection(ok=False, reason=f"MANIFEST.json unreadable: {exc}")
    if not isinstance(manifest, dict):
        return BaselineInspection(ok=False, reason="MANIFEST.json is not an object")
    try:
        listed = _listed_files(manifest)
    except ValueError as exc:
        return BaselineInspection(ok=False, reason=str(exc))
    try:
        baseline_resolved = baseline_dir.resolve()
    except OSError as exc:
        return BaselineInspection(
            ok=False, reason=f"baseline directory unreadable: {exc}"
        )
    for relative, expected in listed:
        path = baseline_dir / relative
        try:
            resolved = path.resolve()
        except OSError as exc:
            return BaselineInspection(ok=False, reason=f"{relative} unreadable: {exc}")
        if not resolved.is_relative_to(baseline_resolved):
            return BaselineInspection(
                ok=False, reason=f"{relative} escapes baseline dir"
            )
        if not resolved.is_file():
            return BaselineInspection(ok=False, reason=f"{relative} missing")
        try:
            actual = sha256_file(resolved)
        except OSError as exc:
            return BaselineInspection(ok=False, reason=f"{relative} unreadable: {exc}")
        if actual != expected:
            return BaselineInspection(
                ok=False, reason=f"{relative} sha256 mismatch"
            )
    class_map_path = baseline_dir / CLASS_MAP_NAME
    loaded, error = load_class_map(class_map_path)
    if error is not None:
        return BaselineInspection(ok=False, reason=error)
    model_name = str(manifest["model"]["file"])
    return BaselineInspection(
        ok=True,
        reason="",
        class_map=loaded,
        model_path=baseline_dir / model_name,
        manifest=manifest,
    )


def load_class_map(
    path: Path,
) -> tuple[dict[str, tuple[int, ...]] | None, str | None]:
    """Read class_map.json from disk. Mapping is never hard-coded (REQ-F-BASE-009)."""

    if not path.is_file():
        return None, "class_map.json missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"class_map.json unreadable: {exc}"
    if not isinstance(payload, dict):
        return None, "class_map.json is not an object"
    classes = payload.get("classes")
    if not isinstance(classes, dict):
        return None, "class_map.json classes is missing"
    keys = set(classes)
    expected = set(CLASS_IDS)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        return None, f"class_map keys mismatch missing={missing} extra={extra}"
    mapped: dict[str, tuple[int, ...]] = {}
    seen: dict[int, str] = {}
    for class_id in CLASS_IDS:
        raw_indices = classes[class_id]
        if not isinstance(raw_indices, list):
            return None, f"class_map[{class_id}] is not a list"
        indices: list[int] = []
        for item in raw_indices:
            if not isinstance(item, int) or isinstance(item, bool):
                return None, f"class_map[{class_id}] has a non-integer index"
            if item < 0 or item >= IMAGENET_CLASS_COUNT:
                return None, f"class_map[{class_id}] index {item} out of range"
            if item in seen:
                return None, (
                    f"imagenet index {item} mapped to both {seen[item]} and {class_id}"
                )
            seen[item] = class_id
            indices.append(item)
        mapped[class_id] = tuple(indices)
    return mapped, None


def register_baseline_model(store: Store, assets_dir: Path) -> BaselineInspection:
    """Register version 0 when assets validate. Never write under assets/."""

    try:
        inspection = inspect_baseline_assets(assets_dir)
    except OSError as exc:
        inspection = BaselineInspection(
            ok=False, reason=f"assets unreadable: {exc}"
        )
    if not inspection.ok:
        LOGGER.warning(
            "baseline model version 0 not registered: %s", inspection.reason
        )
        store.unpublish_builtin()
        return inspection
    store.ensure_builtin_model(ref=str(uuid.uuid4()), created_at=_utc_now_z())
    store.activate_if_none_active(version=0)
    return inspection


def _listed_files(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    model = manifest.get("model")
    if not isinstance(model, dict):
        raise ValueError("MANIFEST.json model is missing")
    file_name = model.get("file")
    digest = model.get("sha256")
    if (
        not isinstance(file_name, str)
        or not _is_basename(file_name)
        or not isinstance(digest, str)
        or not digest
    ):
        raise ValueError("MANIFEST.json model.file/sha256 is invalid")
    items = [(file_name, digest.lower())]
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("MANIFEST.json files is missing")
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("MANIFEST.json files entry is invalid")
        relative = entry.get("file")
        file_digest = entry.get("sha256")
        if (
            not isinstance(relative, str)
            or not _is_basename(relative)
            or not isinstance(file_digest, str)
        ):
            raise ValueError("MANIFEST.json files entry is invalid")
        items.append((relative, file_digest.lower()))
    names = [name for name, _digest in items]
    if len(names) != len(set(names)):
        raise ValueError("MANIFEST.json lists a file more than once")
    if CLASS_MAP_NAME not in names:
        raise ValueError("MANIFEST.json does not list class_map.json")
    return items


def _is_basename(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return path.name == value and "/" not in value and "\\" not in value


def _utc_now_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
