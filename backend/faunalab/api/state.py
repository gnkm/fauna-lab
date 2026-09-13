"""Adapter that maps internal state to SRS vocabulary for GET /api/_state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from faunalab.persist.store import (
    ImageRow,
    InferenceRow,
    JobRow,
    ModelRow,
    Store,
)

router = APIRouter()

_REQUIRED_KEYS = (
    "schema_version",
    "observed_at",
    "classes",
    "images",
    "jobs",
    "models",
    "inferences",
)


def utc_now_z(now: datetime | None = None) -> str:
    moment = now if now is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    else:
        moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_observation_state(
    store: Store, *, now: datetime | None = None
) -> dict[str, Any]:
    """Convert persisted rows into REQ-OBS-002. Does not write."""

    payload: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": utc_now_z(now),
        "classes": [
            {"class_id": row.class_id, "display_order": row.display_order}
            for row in store.list_classes()
        ],
        "images": [_image_to_obs(row) for row in store.list_images()],
        "jobs": [_job_to_obs(row) for row in store.list_jobs()],
        "models": [_model_to_obs(row) for row in store.list_models()],
        "inferences": [_inference_to_obs(row) for row in store.list_inferences()],
    }
    missing = [key for key in _REQUIRED_KEYS if key not in payload]
    if missing:
        raise RuntimeError(f"observation payload missing keys: {missing}")
    return payload


def _image_to_obs(row: ImageRow) -> dict[str, Any]:
    label = None
    if row.label_class_id is not None and row.label_source is not None:
        label = {"class_id": row.label_class_id, "source": row.label_source}
    suggestion = None
    if (
        row.suggestion_class_id is not None
        and row.suggestion_confidence is not None
        and row.suggestion_model_ref is not None
    ):
        suggestion = {
            "class_id": row.suggestion_class_id,
            "confidence": row.suggestion_confidence,
            "model_ref": row.suggestion_model_ref,
        }
    return {
        "ref": row.ref,
        "sha256": row.sha256,
        "split": row.split,
        "label": label,
        "suggestion": suggestion,
    }


def _job_to_obs(row: JobRow) -> dict[str, Any]:
    return {
        "ref": row.ref,
        "status": row.status,
        "current_epoch": row.current_epoch,
        "total_epochs": row.total_epochs,
        "model_ref": row.model_ref,
        "failed": row.status == "FAILED",
    }


def _model_to_obs(row: ModelRow) -> dict[str, Any]:
    return {
        "ref": row.ref,
        "version": row.version,
        "builtin": row.builtin,
        "active": row.active,
        "metrics": row.metrics,
    }


def _inference_to_obs(row: InferenceRow) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ref": row.ref,
        "image_ref": row.image_ref,
        "model_ref": row.model_ref,
        "top_class_id": row.top_class_id,
        "top_confidence": row.top_confidence,
        "other_mass": row.other_mass,
        "low_confidence": row.low_confidence,
        "created_at": row.created_at,
    }
    if row.scores is not None:
        body["scores"] = row.scores
    return body


@router.get("/api/_state")
def get_state(request: Request) -> dict[str, Any]:
    store: Store = request.app.state.store
    return build_observation_state(store)
