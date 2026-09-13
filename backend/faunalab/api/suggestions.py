"""Label suggestion program interface (F012 / REQ-F-SUG-001〜010)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from faunalab.api.errors import (
    baseline_unavailable,
    error_for_code,
    image_not_found,
    no_active_model,
    suggestion_not_found,
)
from faunalab.api.state import utc_now_z
from faunalab.domain.suggestions import MAX_SUGGESTION_IMAGES
from faunalab.ml.runtime import BaselineRuntime
from faunalab.persist.files import resolve_under
from faunalab.persist.store import (
    ImageNotFoundError,
    ImageRow,
    ModelNotFoundError,
    ModelRow,
    Store,
    SuggestionNew,
    SuggestionNotFoundError,
    SuggestionRow,
)

router = APIRouter()


class SuggestionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refs: list[str] | None = Field(default=None, max_length=MAX_SUGGESTION_IMAGES)


class RefListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refs: list[str] = Field(min_length=1)


class ThresholdAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_confidence: float = Field(ge=0, le=1)


def _store(request: Request) -> Store:
    return request.app.state.store


def _runtime(request: Request) -> BaselineRuntime | None:
    return getattr(request.app.state, "baseline_runtime", None)


def _suggestion_to_api(row: SuggestionRow) -> dict[str, Any]:
    return {
        "image_ref": row.image_ref,
        "class_id": row.class_id,
        "confidence": row.confidence,
        "model_ref": row.model_ref,
    }


def _pil_from_store(store: Store, row: ImageRow) -> Image.Image:
    path = resolve_under(store.data_dir, row.path)
    with Image.open(path) as loaded:
        loaded.load()
        return loaded.copy()


def _require_active_runtime(
    request: Request,
) -> tuple[Store, ModelRow, BaselineRuntime]:
    store = _store(request)
    model = store.get_active_model()
    if model is None:
        raise no_active_model()
    runtime = _runtime(request)
    if not model.builtin or runtime is None:
        raise baseline_unavailable()
    return store, model, runtime


def _parse_refs(raw: list[str]) -> list[str]:
    refs = [item.strip() for item in raw]
    if any(not item for item in refs):
        raise error_for_code("validation_error", "refs に空の値が含まれています。")
    return refs


def _parse_create_refs(body: SuggestionCreateRequest | None) -> list[str] | None:
    if body is None or body.refs is None:
        return None
    refs = _parse_refs(body.refs)
    if not refs:
        raise error_for_code(
            "validation_error",
            "refs が空です。省略するか 1 件以上指定してください。",
        )
    if len(refs) > MAX_SUGGESTION_IMAGES:
        raise error_for_code(
            "validation_error",
            "1 回の要求で処理できる画像は 100 枚までです。",
        )
    return refs


def _unlabeled_targets(store: Store) -> list[ImageRow]:
    items, _total = store.list_images_page(
        split=None,
        class_id=None,
        labeled=False,
        limit=MAX_SUGGESTION_IMAGES,
        offset=0,
    )
    return items


@router.get("/api/suggestions")
def list_suggestions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    order: Literal["asc", "desc"] = "desc",
) -> dict[str, Any]:
    if (
        min_confidence is not None
        and max_confidence is not None
        and min_confidence > max_confidence
    ):
        raise error_for_code(
            "validation_error",
            "min_confidence は max_confidence 以下である必要があります。",
        )
    items, total = _store(request).list_suggestions_page(
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        order=order,
        limit=limit,
        offset=offset,
    )
    return {"items": [_suggestion_to_api(row) for row in items], "total": total}


@router.post("/api/suggestions")
def create_suggestions(
    request: Request,
    body: SuggestionCreateRequest | None = None,
) -> dict[str, Any]:
    refs = _parse_create_refs(body)
    store, model, runtime = _require_active_runtime(request)
    skipped_labeled = 0
    if refs is None:
        targets = _unlabeled_targets(store)
    else:
        try:
            rows = store.get_images_by_refs(refs)
        except ImageNotFoundError as exc:
            raise image_not_found() from exc
        targets = []
        seen: set[str] = set()
        for row in rows:
            if row.ref in seen:
                continue
            seen.add(row.ref)
            if row.label_class_id is not None:
                skipped_labeled += 1
                continue
            targets.append(row)

    if not targets:
        return {
            "generated_count": 0,
            "skipped_labeled_count": skipped_labeled,
        }

    pil_images: list[Image.Image] = []
    try:
        for row in targets:
            pil_images.append(_pil_from_store(store, row))
        folded = runtime.infer_images(pil_images)
        created_at = utc_now_z()
        items = [
            SuggestionNew(
                image_ref=row.ref,
                class_id=result.top_class_id,
                confidence=float(result.top_confidence),
                created_at=created_at,
            )
            for row, result in zip(targets, folded, strict=True)
        ]
        try:
            generated, skipped_on_save = store.upsert_suggestions(
                model_ref=model.ref, items=items
            )
        except ImageNotFoundError as exc:
            raise image_not_found() from exc
        except ModelNotFoundError as exc:
            raise no_active_model() from exc
    finally:
        for image in pil_images:
            image.close()
    return {
        "generated_count": generated,
        "skipped_labeled_count": skipped_labeled + skipped_on_save,
    }


@router.post("/api/suggestions/accept")
def accept_suggestions(request: Request, body: RefListRequest) -> dict[str, Any]:
    refs = _parse_refs(body.refs)
    try:
        updated = _store(request).accept_suggestions(refs, utc_now_z())
    except ImageNotFoundError as exc:
        raise image_not_found() from exc
    return {"updated_count": updated}


@router.post("/api/suggestions/accept-by-threshold")
def accept_suggestions_by_threshold(
    request: Request, body: ThresholdAcceptRequest
) -> dict[str, Any]:
    updated = _store(request).accept_suggestions_by_threshold(
        body.min_confidence, utc_now_z()
    )
    return {"updated_count": updated}


@router.post("/api/suggestions/reject")
def reject_suggestions(request: Request, body: RefListRequest) -> dict[str, Any]:
    refs = _parse_refs(body.refs)
    try:
        updated = _store(request).delete_suggestions(refs)
    except SuggestionNotFoundError as exc:
        raise suggestion_not_found() from exc
    return {"updated_count": updated}
