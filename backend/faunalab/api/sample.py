"""Sample dataset import (F009 / REQ-F-SYS-003)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from faunalab.api.errors import error_for_code
from faunalab.api.state import utc_now_z
from faunalab.domain.images import normalize_original_name
from faunalab.domain.ingest import ingest_image_bytes
from faunalab.domain.sample import (
    SampleManifestError,
    SampleUnavailableError,
    load_sample_items,
)
from faunalab.persist.store import Store
from faunalab.settings import Settings

router = APIRouter()


@router.post("/api/sample/import")
def import_sample(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    store: Store = request.app.state.store
    try:
        items = load_sample_items(settings.assets_dir)
    except SampleUnavailableError as exc:
        raise error_for_code("sample_unavailable", str(exc)) from exc
    except SampleManifestError as exc:
        raise error_for_code("validation_error", str(exc)) from exc

    assigned_at = utc_now_z()
    labeled_refs: list[str] = []
    for item in items:
        try:
            data = item.path.read_bytes()
        except OSError as exc:
            raise error_for_code(
                "sample_unavailable",
                f"サンプル画像を読めません: {item.file}",
            ) from exc
        filename = normalize_original_name(item.path.name)
        result = ingest_image_bytes(
            store,
            data,
            filename,
            created_at=assigned_at,
            allow_duplicate=True,
        )
        if not result.ok or result.ref is None:
            raise error_for_code(
                "sample_unavailable",
                f"サンプル画像を登録できません: {item.file}",
            )
        if not store.upsert_label(result.ref, item.class_id, "human", assigned_at):
            raise error_for_code(
                "internal_error",
                "処理中に予期しない誤りが起きました。",
            )
        labeled_refs.append(result.ref)
    return {"updated_count": len(labeled_refs)}
