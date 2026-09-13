"""Register image bytes into the data directory and SQLite store."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from faunalab.domain.images import (
    UnsupportedImageError,
    decode_and_thumbnail,
    image_relpath,
    sha256_hex,
    thumb_relpath,
)
from faunalab.persist.files import remove_if_present, write_bytes
from faunalab.persist.store import DuplicateImageError, Store


@dataclass(frozen=True, slots=True)
class IngestResult:
    ok: bool
    ref: str | None
    created: bool
    code: str | None


def ingest_image_bytes(
    store: Store,
    data: bytes,
    filename: str,
    *,
    created_at: str,
    allow_duplicate: bool = False,
) -> IngestResult:
    """Write files then insert. Duplicates fail unless `allow_duplicate`."""

    try:
        decoded = decode_and_thumbnail(data)
    except UnsupportedImageError:
        return IngestResult(
            ok=False, ref=None, created=False, code="unsupported_media_type"
        )
    digest = sha256_hex(data)
    existing = store.get_image_by_sha256(digest)
    if existing is not None:
        if allow_duplicate:
            return IngestResult(ok=True, ref=existing.ref, created=False, code=None)
        return IngestResult(ok=False, ref=None, created=False, code="image_duplicate")
    image_rel = image_relpath(digest, decoded.fmt)
    thumb_rel = thumb_relpath(digest)
    ref = str(uuid.uuid4())
    written: list[str] = []
    try:
        write_bytes(store.data_dir, image_rel, data)
        written.append(image_rel)
        write_bytes(store.data_dir, thumb_rel, decoded.thumbnail_jpeg)
        written.append(thumb_rel)
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
        if allow_duplicate:
            reused = store.get_image_by_sha256(digest)
            if reused is not None:
                return IngestResult(ok=True, ref=reused.ref, created=False, code=None)
        return IngestResult(ok=False, ref=None, created=False, code="image_duplicate")
    except Exception:
        if not store.sha256_exists(digest):
            for relative in written:
                try:
                    remove_if_present(store.data_dir, relative)
                except (OSError, ValueError):
                    pass
        raise
    return IngestResult(ok=True, ref=ref, created=True, code=None)
