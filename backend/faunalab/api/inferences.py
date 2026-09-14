"""Inference program interface (F011 / REQ-F-INF-001〜009)."""

from __future__ import annotations

import io
import json
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from faunalab.api.active_infer import infer_images_for_model
from faunalab.api.errors import (
    AppError,
    baseline_unavailable,
    error_for_code,
    image_not_found,
    no_active_model,
)
from faunalab.api.images import _read_size_header, _read_upload
from faunalab.api.state import _inference_to_obs, utc_now_z
from faunalab.domain.images import (
    MAX_IMAGE_BYTES,
    UnsupportedImageError,
    decode_and_thumbnail,
    thumb_relpath,
)
from faunalab.domain.inferences import (
    MAX_INFERENCE_IMAGES,
    is_low_confidence,
    other_mass_for_model,
    ranked_scores,
)
from faunalab.domain.ingest import ingest_image_bytes
from faunalab.ml.runtime import BaselineRuntime
from faunalab.persist.files import remove_if_present, resolve_under
from faunalab.persist.store import (
    ImageNotFoundError,
    ImageRow,
    InferenceNew,
    InferenceRow,
    ModelNotFoundError,
    Store,
)
from faunalab.settings import Settings

router = APIRouter()

_MAX_REQUEST_BYTES = MAX_INFERENCE_IMAGES * MAX_IMAGE_BYTES + 2 * 1024 * 1024


class InferenceCreateJson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refs: list[str] = Field(min_length=1, max_length=MAX_INFERENCE_IMAGES)


def _store(request: Request) -> Store:
    return request.app.state.store


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _runtime(request: Request) -> BaselineRuntime | None:
    return getattr(request.app.state, "baseline_runtime", None)


def inference_to_api(row: InferenceRow) -> dict[str, Any]:
    body = _inference_to_obs(row)
    if "scores" not in body:
        body["scores"] = row.scores if row.scores is not None else []
    return body


def _pil_from_bytes(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as loaded:
        loaded.load()
        return loaded.copy()


def _pil_from_store(store: Store, row: ImageRow) -> Image.Image:
    path = resolve_under(store.data_dir, row.path)
    with Image.open(path) as loaded:
        loaded.load()
        return loaded.copy()


def _parse_ref_fields(values: list[Any]) -> list[str]:
    refs: list[str] = []
    for value in values:
        if isinstance(value, UploadFile):
            continue
        text = str(value).strip()
        if not text:
            raise error_for_code("validation_error", "refs に空の値が含まれています。")
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise error_for_code(
                    "validation_error",
                    "refs の JSON が不正です。",
                ) from exc
            if not isinstance(parsed, list):
                raise error_for_code(
                    "validation_error",
                    "refs は配列である必要があります。",
                )
            for item in parsed:
                if not isinstance(item, str) or not item.strip():
                    raise error_for_code("validation_error", "refs の要素が不正です。")
                refs.append(item.strip())
        else:
            refs.append(text)
    return refs


async def _parse_json_refs(request: Request) -> list[str]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise error_for_code("validation_error", "要求の内容が不正です。") from exc
    try:
        body = InferenceCreateJson.model_validate(payload)
    except ValidationError as exc:
        raise error_for_code("validation_error", "要求の内容が不正です。") from exc
    refs = [item.strip() for item in body.refs]
    if any(not item for item in refs):
        raise error_for_code("validation_error", "refs に空の値が含まれています。")
    return refs


async def _parse_multipart(
    request: Request,
) -> tuple[list[tuple[bytes, str]], list[str]]:
    try:
        async with request.form(
            max_files=MAX_INFERENCE_IMAGES,
            max_fields=MAX_INFERENCE_IMAGES + 10,
            max_part_size=MAX_IMAGE_BYTES,
        ) as form:
            return await _files_and_refs_from_form(form)
    except AppError:
        raise
    except StarletteHTTPException as exc:
        detail = str(exc.detail).lower()
        if "exceeded maximum size" in detail:
            raise error_for_code(
                "payload_too_large",
                "ファイルサイズが 10 MiB を超えています。",
            ) from exc
        if "too many files" in detail:
            raise error_for_code(
                "validation_error",
                "1 回の要求で処理できる画像は 20 枚までです。",
            ) from exc
        raise error_for_code("validation_error", "要求の内容が不正です。") from exc


async def _files_and_refs_from_form(
    form: FormData,
) -> tuple[list[tuple[bytes, str]], list[str]]:
    uploads = [item for item in form.getlist("files") if isinstance(item, UploadFile)]
    files: list[tuple[bytes, str]] = []
    for upload in uploads:
        data, filename = await _read_upload(upload)
        if data is None:
            raise error_for_code(
                "payload_too_large",
                "ファイルサイズが 10 MiB を超えています。",
            )
        files.append((data, filename))
    refs = _parse_ref_fields(list(form.getlist("refs")))
    return files, refs


def _require_count(file_count: int, ref_count: int) -> None:
    total = file_count + ref_count
    if total < 1:
        raise error_for_code(
            "validation_error",
            "files または refs を 1 件以上指定してください。",
        )
    if total > MAX_INFERENCE_IMAGES:
        raise error_for_code(
            "validation_error",
            "1 回の要求で処理できる画像は 20 枚までです。",
        )


def _rollback_created_images(store: Store, refs: list[str]) -> None:
    """推論要求が失敗したとき、この要求で新規登録した画像だけを戻す。"""

    for ref in refs:
        row = store.delete_image(ref)
        if row is None:
            continue
        for relative in (row.path, thumb_relpath(row.sha256)):
            try:
                remove_if_present(store.data_dir, relative)
            except (OSError, ValueError):
                pass


@router.get("/api/inferences")
def list_inferences(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = _store(request).list_inferences_page(limit=limit, offset=offset)
    return {"items": [inference_to_api(row) for row in items], "total": total}


@router.post("/api/inferences")
async def create_inferences(request: Request) -> dict[str, Any]:
    length = _read_size_header(request)
    if length is not None and length > _MAX_REQUEST_BYTES:
        raise error_for_code(
            "payload_too_large",
            "要求全体の大きさが上限を超えています。",
        )
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        files: list[tuple[bytes, str]] = []
        refs = await _parse_json_refs(request)
    elif content_type.startswith("multipart/form-data"):
        files, refs = await _parse_multipart(request)
    else:
        raise error_for_code(
            "validation_error",
            "JSON または multipart/form-data で送ってください。",
        )
    _require_count(len(files), len(refs))

    store = _store(request)
    settings = _settings(request)
    model = store.get_active_model()
    if model is None:
        raise no_active_model()
    runtime = _runtime(request)
    if model.builtin and runtime is None:
        raise baseline_unavailable()

    for data, _filename in files:
        try:
            decode_and_thumbnail(data)
        except UnsupportedImageError as exc:
            raise error_for_code(
                "unsupported_media_type",
                "JPEG または PNG として解釈できません。",
            ) from exc

    ref_rows: list[ImageRow] = []
    for ref in refs:
        row = store.get_image(ref)
        if row is None:
            raise image_not_found()
        ref_rows.append(row)

    created_at = utc_now_z()
    image_refs: list[str] = []
    pil_images: list[Image.Image] = []
    created_image_refs: list[str] = []
    try:
        for data, _filename in files:
            pil_images.append(_pil_from_bytes(data))
        for row in ref_rows:
            pil_images.append(_pil_from_store(store, row))

        started = time.perf_counter()
        folded = infer_images_for_model(request, store, model, pil_images)
        duration_ms = int((time.perf_counter() - started) * 1000)

        for data, filename in files:
            ingested = ingest_image_bytes(
                store,
                data,
                filename,
                created_at=created_at,
                allow_duplicate=True,
            )
            if not ingested.ok or ingested.ref is None:
                code = ingested.code or "internal_error"
                if code == "unsupported_media_type":
                    raise error_for_code(
                        "unsupported_media_type",
                        "JPEG または PNG として解釈できません。",
                    )
                raise error_for_code(code, "画像を登録できませんでした。")
            image_refs.append(ingested.ref)
            if ingested.created:
                created_image_refs.append(ingested.ref)
        for row in ref_rows:
            image_refs.append(row.ref)

        records: list[InferenceNew] = []
        for image_ref, result in zip(image_refs, folded, strict=True):
            mass = other_mass_for_model(builtin=model.builtin, folded=result)
            low = is_low_confidence(
                result,
                confidence_threshold=settings.confidence_threshold,
                other_mass_threshold=settings.other_mass_threshold,
                other_mass=mass,
            )
            records.append(
                InferenceNew(
                    ref=str(uuid.uuid4()),
                    image_ref=image_ref,
                    top_class_id=result.top_class_id,
                    top_confidence=float(result.top_confidence),
                    other_mass=mass,
                    low_confidence=low,
                    scores=ranked_scores(result.scores),
                    created_at=created_at,
                    duration_ms=duration_ms,
                )
            )
        try:
            saved = store.insert_inferences(model_ref=model.ref, items=records)
        except ImageNotFoundError as exc:
            raise image_not_found() from exc
        except ModelNotFoundError as exc:
            raise no_active_model() from exc
        return {"items": [inference_to_api(row) for row in saved]}
    except Exception:
        _rollback_created_images(store, created_image_refs)
        raise
    finally:
        for image in pil_images:
            image.close()
