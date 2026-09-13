"""Confirmed labels (F009 / REQ-F-ANN-001〜007)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from faunalab.api.errors import image_not_found
from faunalab.api.state import utc_now_z
from faunalab.domain.classes import ClassId, LabelSource
from faunalab.persist.store import ImageNotFoundError, Store

router = APIRouter()


class LabelWrite(BaseModel):
    class_id: ClassId
    source: LabelSource = "human"


class BulkLabelRequest(BaseModel):
    refs: list[str] = Field(min_length=1)
    class_id: ClassId


def _store(request: Request) -> Store:
    return request.app.state.store


@router.put("/api/images/{ref}/label")
def put_image_label(request: Request, ref: str, body: LabelWrite) -> dict[str, Any]:
    assigned_at = utc_now_z()
    ok = _store(request).upsert_label(ref, body.class_id, body.source, assigned_at)
    if not ok:
        raise image_not_found()
    return {"class_id": body.class_id, "source": body.source}


@router.delete("/api/images/{ref}/label", status_code=204)
def delete_image_label(request: Request, ref: str) -> None:
    result = _store(request).delete_label(ref)
    if result is None:
        raise image_not_found()


@router.post("/api/labels/bulk")
def bulk_put_labels(request: Request, body: BulkLabelRequest) -> dict[str, Any]:
    try:
        updated = _store(request).upsert_labels_bulk(
            body.refs, body.class_id, "human", utc_now_z()
        )
    except ImageNotFoundError:
        raise image_not_found() from None
    return {"updated_count": updated}
