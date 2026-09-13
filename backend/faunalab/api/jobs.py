"""Training job program interface (F014 / REQ-F-TRN-001〜017)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from faunalab.api.errors import error_for_code, job_not_found
from faunalab.api.state import _job_to_obs, utc_now_z
from faunalab.domain.jobs import (
    DEFAULT_AUGMENTATION,
    DEFAULT_BATCH_SIZE,
    DEFAULT_EPOCHS,
    DEFAULT_LEARNING_RATE,
    DEFAULT_SEED,
    DEFAULT_USE_BASELINE,
    BaselineUnavailableError,
    JobNotCancelableError,
    JobNotFoundError,
    JobParams,
    TrainingPreconditionError,
    enqueue_job,
    request_cancel,
)
from faunalab.persist.store import JobRow, Store

router = APIRouter()


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    epochs: int = Field(default=DEFAULT_EPOCHS, ge=1)
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1)
    learning_rate: float = Field(default=DEFAULT_LEARNING_RATE, gt=0)
    seed: int = DEFAULT_SEED
    augmentation: bool = DEFAULT_AUGMENTATION
    use_baseline: bool = DEFAULT_USE_BASELINE


def _store(request: Request) -> Store:
    return request.app.state.store


def _job_to_api(row: JobRow) -> dict[str, Any]:
    return _job_to_obs(row)


@router.get("/api/jobs")
def list_jobs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = _store(request).list_jobs_page(limit=limit, offset=offset)
    return {"items": [_job_to_api(row) for row in items], "total": total}


@router.post("/api/jobs")
def create_job(request: Request, body: JobCreateRequest | None = None) -> JSONResponse:
    payload = body if body is not None else JobCreateRequest()
    params = JobParams(
        epochs=payload.epochs,
        batch_size=payload.batch_size,
        learning_rate=payload.learning_rate,
        seed=payload.seed,
        augmentation=payload.augmentation,
        use_baseline=payload.use_baseline,
    )
    try:
        ref = enqueue_job(
            _store(request),
            params,
            created_at=utc_now_z(),
            baseline=request.app.state.baseline,
        )
    except TrainingPreconditionError as exc:
        raise error_for_code(
            "training_precondition",
            "学習を開始するための枚数またはクラス数が足りません。",
        ) from exc
    except BaselineUnavailableError as exc:
        raise error_for_code(
            "baseline_unavailable",
            "ベースラインモデルの資産を利用できません。",
        ) from exc
    row = _store(request).get_job(ref)
    if row is None:
        raise error_for_code("internal_error", "学習ジョブを登録できませんでした。")
    return JSONResponse(
        status_code=201,
        content=_job_to_api(row),
        headers={"Location": f"/api/jobs/{ref}"},
    )


@router.get("/api/jobs/{ref}")
def get_job(request: Request, ref: str) -> dict[str, Any]:
    row = _store(request).get_job(ref)
    if row is None:
        raise job_not_found()
    return _job_to_api(row)


@router.get("/api/jobs/{ref}/logs")
def get_job_logs(
    request: Request,
    ref: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    store = _store(request)
    if store.get_job(ref) is None:
        raise job_not_found()
    items, total = store.list_job_logs_page(ref, limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.post("/api/jobs/{ref}/cancel")
def cancel_job(request: Request, ref: str) -> dict[str, Any]:
    try:
        request_cancel(_store(request), ref)
    except JobNotFoundError as exc:
        raise job_not_found() from exc
    except JobNotCancelableError as exc:
        raise error_for_code(
            "job_not_cancelable",
            "終端状態のジョブは中止できません。",
        ) from exc
    row = _store(request).get_job(ref)
    if row is None:
        raise job_not_found()
    return _job_to_api(row)
