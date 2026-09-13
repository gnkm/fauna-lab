"""Image program interface (F008 / REQ-F-IMG-001〜009)."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from faunalab.api.errors import (
    AppError,
    error_for_code,
    image_not_found,
)
from faunalab.api.state import _image_to_obs, utc_now_z
from faunalab.domain.images import (
    MAX_IMAGE_BYTES,
    MAX_UPLOAD_FILES,
    UnsupportedImageError,
    decode_and_thumbnail,
    image_relpath,
    media_type_from_path,
    normalize_original_name,
    sha256_hex,
    thumb_relpath,
)
from faunalab.persist.files import remove_if_present, resolve_under, write_bytes
from faunalab.persist.store import DuplicateImageError, ImageRow, Store

LOGGER = logging.getLogger("faunalab.api.images")

router = APIRouter()

Split = Literal["train", "val", "test", "unassigned"]
ClassId = Literal[
    "samoyed",
    "great_pyrenees",
    "boxer",
    "american_bulldog",
    "chihuahua",
    "miniature_pinscher",
    "pomeranian",
    "havanese",
]

_MAX_REQUEST_BYTES = MAX_UPLOAD_FILES * MAX_IMAGE_BYTES + 2 * 1024 * 1024

_ITEM_DETAIL: dict[str, str] = {
    "payload_too_large": "ファイルサイズが 10 MiB を超えています。",
    "unsupported_media_type": "JPEG または PNG として解釈できません。",
    "image_duplicate": "同一内容の画像が既に登録されています。",
    "validation_error": "要求の内容が不正です。",
}


def _store(request: Request) -> Store:
    return request.app.state.store


def _image_to_api(row: ImageRow) -> dict[str, Any]:
    body = _image_to_obs(row)
    body.update(
        {
            "original_name": row.original_name,
            "size_bytes": row.size_bytes,
            "width": row.width,
            "height": row.height,
            "created_at": row.created_at,
            "media_type": media_type_from_path(row.path),
        }
    )
    return body


def _failed_item(filename: str, code: str) -> dict[str, Any]:
    return {
        "filename": filename,
        "ok": False,
        "code": code,
        "detail": _ITEM_DETAIL[code],
    }


def _ok_item(filename: str, ref: str) -> dict[str, Any]:
    return {"filename": filename, "ok": True, "ref": ref}


def _read_size_header(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _read_upload(upload: UploadFile) -> tuple[bytes | None, str]:
    filename = normalize_original_name(upload.filename)
    declared = upload.size
    if declared is not None and declared > MAX_IMAGE_BYTES:
        await upload.close()
        return None, filename
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            await upload.close()
            return None, filename
        chunks.append(chunk)
    await upload.close()
    return b"".join(chunks), filename


def _register_one(store: Store, filename: str, data: bytes) -> dict[str, Any]:
    try:
        decoded = decode_and_thumbnail(data)
    except UnsupportedImageError:
        return _failed_item(filename, "unsupported_media_type")
    digest = sha256_hex(data)
    if store.sha256_exists(digest):
        return _failed_item(filename, "image_duplicate")
    image_rel = image_relpath(digest, decoded.fmt)
    thumb_rel = thumb_relpath(digest)
    ref = str(uuid.uuid4())
    created_at = utc_now_z()
    try:
        store.insert_image(
            ref=ref,
            sha256=digest,
            original_name=filename,
            size_bytes=len(data),
            width=decoded.width,
            height=decoded.height,
            path=image_rel,
            created_at=created_at,
        )
    except DuplicateImageError:
        # 共有パスのファイルは勝った側のものなので消さない。
        return _failed_item(filename, "image_duplicate")
    written: list[str] = []
    try:
        write_bytes(store.data_dir, image_rel, data)
        written.append(image_rel)
        write_bytes(store.data_dir, thumb_rel, decoded.thumbnail_jpeg)
        written.append(thumb_rel)
    except Exception:
        store.delete_image(ref)
        for relative in written:
            _remove_stored_file(store, relative)
        raise
    return _ok_item(filename, ref)


def _remove_stored_file(store: Store, relative: str) -> None:
    if not relative:
        return
    try:
        remove_if_present(store.data_dir, relative)
    except ValueError:
        LOGGER.warning("refused to delete path outside data dir")
    except OSError:
        LOGGER.warning("failed to remove stored file %s", relative)


def _upload_http_result(items: list[dict[str, Any]]) -> JSONResponse | dict[str, Any]:
    if len(items) == 1 and not items[0]["ok"]:
        code = str(items[0]["code"])
        return error_for_code(code, str(items[0]["detail"])).to_response()
    return {"items": items}


@router.post("/api/images")
async def upload_images(request: Request) -> Any:
    length = _read_size_header(request)
    if length is not None and length > _MAX_REQUEST_BYTES:
        raise error_for_code(
            "payload_too_large",
            "要求全体の大きさが上限を超えています。",
        )
    try:
        async with request.form(
            max_files=MAX_UPLOAD_FILES,
            max_fields=10,
            max_part_size=MAX_IMAGE_BYTES,
        ) as form:
            raw_files = form.getlist("files")
            uploads = [item for item in raw_files if isinstance(item, UploadFile)]
            if not uploads:
                raise error_for_code(
                    "validation_error",
                    "files フィールドに 1 件以上のファイルが必要です。",
                )
            if len(uploads) > MAX_UPLOAD_FILES:
                raise error_for_code(
                    "validation_error",
                    "1 回の操作で受け取れるファイルは 50 件までです。",
                )
            items: list[dict[str, Any]] = []
            store = _store(request)
            for upload in uploads:
                data, filename = await _read_upload(upload)
                if data is None:
                    items.append(_failed_item(filename, "payload_too_large"))
                    continue
                items.append(_register_one(store, filename, data))
            return _upload_http_result(items)
    except AppError:
        raise
    except StarletteHTTPException as exc:
        detail = str(exc.detail)
        lowered = detail.lower()
        if "exceeded maximum size" in lowered:
            raise error_for_code(
                "payload_too_large",
                "ファイルサイズが 10 MiB を超えています。",
            ) from exc
        if "too many files" in lowered:
            raise error_for_code(
                "validation_error",
                "1 回の操作で受け取れるファイルは 50 件までです。",
            ) from exc
        raise error_for_code("validation_error", "要求の内容が不正です。") from exc


@router.get("/api/images")
def list_images(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    split: Split | None = None,
    class_id: ClassId | None = None,
    labeled: bool | None = None,
) -> dict[str, Any]:
    items, total = _store(request).list_images_page(
        split=split,
        class_id=class_id,
        labeled=labeled,
        limit=limit,
        offset=offset,
    )
    return {"items": [_image_to_api(row) for row in items], "total": total}


@router.get("/api/images/{ref}")
def get_image(request: Request, ref: str) -> dict[str, Any]:
    row = _store(request).get_image(ref)
    if row is None:
        raise image_not_found()
    return _image_to_api(row)


@router.get("/api/images/{ref}/thumbnail")
def get_thumbnail(request: Request, ref: str) -> FileResponse:
    store = _store(request)
    row = store.get_image(ref)
    if row is None:
        raise image_not_found()
    thumb_rel = thumb_relpath(row.sha256)
    try:
        path = resolve_under(store.data_dir, thumb_rel)
    except ValueError as exc:
        raise error_for_code(
            "internal_error",
            "処理中に予期しない誤りが起きました。",
        ) from exc
    if not path.is_file():
        raise image_not_found()
    return FileResponse(path, media_type="image/jpeg")


@router.delete("/api/images/{ref}", status_code=204)
def delete_image(request: Request, ref: str) -> None:
    store = _store(request)
    row = store.delete_image(ref)
    if row is None:
        raise image_not_found()
    thumb_rel = thumb_relpath(row.sha256)
    for relative in (row.path, thumb_rel):
        _remove_stored_file(store, relative)
