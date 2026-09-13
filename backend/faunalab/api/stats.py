"""Dataset stats (F009 / REQ-F-DS-005)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from faunalab.persist.store import Store

router = APIRouter()


@router.get("/api/stats")
def get_stats(request: Request) -> dict[str, Any]:
    store: Store = request.app.state.store
    return store.stats()
