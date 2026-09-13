"""Dataset split (F009 / REQ-F-DS-001〜004)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator

from faunalab.domain.splits import (
    DEFAULT_SEED,
    DEFAULT_TEST_RATIO,
    DEFAULT_TRAIN_RATIO,
    DEFAULT_VAL_RATIO,
    RatioError,
    stratified_assignments,
    validate_ratios,
)
from faunalab.persist.store import Store

router = APIRouter()


class SplitRequest(BaseModel):
    train_ratio: float = Field(default=DEFAULT_TRAIN_RATIO, gt=0, lt=1)
    val_ratio: float = Field(default=DEFAULT_VAL_RATIO, gt=0, lt=1)
    test_ratio: float = Field(default=DEFAULT_TEST_RATIO, gt=0, lt=1)
    seed: int = DEFAULT_SEED

    @model_validator(mode="after")
    def ratios_sum_to_one(self) -> SplitRequest:
        try:
            validate_ratios(self.train_ratio, self.val_ratio, self.test_ratio)
        except RatioError as exc:
            raise ValueError(str(exc)) from exc
        return self


def _store(request: Request) -> Store:
    return request.app.state.store


@router.post("/api/splits")
def create_split(request: Request, body: SplitRequest | None = None) -> dict[str, Any]:
    payload = body if body is not None else SplitRequest()
    store = _store(request)

    def assign(labeled: list[tuple[str, str]]) -> dict[str, str]:
        return stratified_assignments(
            labeled,
            train_ratio=payload.train_ratio,
            val_ratio=payload.val_ratio,
            test_ratio=payload.test_ratio,
            seed=payload.seed,
        )

    assigned_count, unassigned_count = store.recompute_splits(assign)
    return {
        "assigned_count": assigned_count,
        "unassigned_count": unassigned_count,
        "seed": payload.seed,
        "train_ratio": payload.train_ratio,
        "val_ratio": payload.val_ratio,
        "test_ratio": payload.test_ratio,
    }
