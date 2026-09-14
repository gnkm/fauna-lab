"""Model management program interface (F013 / REQ-F-MDL-001〜009)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from faunalab.api.errors import error_for_code, model_not_found
from faunalab.domain.models import (
    BaselineUnavailableError,
    EmptyTestSplitError,
    ModelArtifactMissingError,
    ModelNotDeletableError,
    ModelNotFoundError,
    activate_model,
    delete_model,
    evaluate_model,
)
from faunalab.persist.store import ModelRow, Store

router = APIRouter()


def _store(request: Request) -> Store:
    return request.app.state.store


def _model_to_api(row: ModelRow) -> dict[str, Any]:
    return {
        "ref": row.ref,
        "version": row.version,
        "builtin": row.builtin,
        "active": row.active,
        "created_at": row.created_at,
        "metrics": row.metrics,
    }


@router.get("/api/models")
def list_models(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = _store(request).list_models_page(limit=limit, offset=offset)
    return {"items": [_model_to_api(row) for row in items], "total": total}


@router.get("/api/models/{ref}")
def get_model(request: Request, ref: str) -> dict[str, Any]:
    row = _store(request).get_model(ref)
    if row is None:
        raise model_not_found()
    return _model_to_api(row)


@router.post("/api/models/{ref}/activate")
def post_activate(request: Request, ref: str) -> dict[str, Any]:
    try:
        row = activate_model(_store(request), ref)
    except ModelNotFoundError as exc:
        raise model_not_found() from exc
    return _model_to_api(row)


@router.post("/api/models/{ref}/evaluate")
def post_evaluate(request: Request, ref: str) -> dict[str, Any]:
    try:
        row = evaluate_model(
            _store(request),
            ref,
            baseline=request.app.state.baseline,
        )
    except ModelNotFoundError as exc:
        raise model_not_found() from exc
    except EmptyTestSplitError as exc:
        raise error_for_code(
            "empty_test_split",
            "試験用分割が空のため再評価できません。",
        ) from exc
    except BaselineUnavailableError as exc:
        raise error_for_code(
            "baseline_unavailable",
            "ベースラインモデルの資産を利用できません。",
        ) from exc
    except ModelArtifactMissingError as exc:
        raise error_for_code(
            "internal_error",
            "モデル成果物を読み込めません。",
        ) from exc
    return _model_to_api(row)


@router.delete("/api/models/{ref}")
def remove_model(request: Request, ref: str) -> Response:
    try:
        delete_model(_store(request), ref)
    except ModelNotFoundError as exc:
        raise model_not_found() from exc
    except ModelNotDeletableError as exc:
        raise error_for_code(
            "model_not_deletable",
            "有効モデルまたはベースラインモデルは削除できません。",
        ) from exc
    except OSError as exc:
        raise error_for_code(
            "internal_error",
            "モデル成果物を除去できません。",
        ) from exc
    return Response(status_code=204)
