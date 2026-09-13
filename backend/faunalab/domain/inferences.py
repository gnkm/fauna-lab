"""Inference scoring helpers (REQ-F-INF-008 / 009). HTTP に依存しない。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from faunalab.domain.classes import CLASS_IDS
from faunalab.ml.fold import FoldResult

MAX_INFERENCE_IMAGES = 20
SCORE_SUM_TOLERANCE = 0.001


def ranked_scores(scores: Mapping[str, float]) -> list[dict[str, Any]]:
    """8 クラスを信頼度の降順に並べる。同率は display_order が小さい方を先にする。"""

    items = [
        {"class_id": class_id, "confidence": float(scores[class_id])}
        for class_id in CLASS_IDS
        if class_id in scores
    ]
    items.sort(
        key=lambda item: (
            -float(item["confidence"]),
            CLASS_IDS.index(str(item["class_id"])),
        )
    )
    return items


def is_low_confidence(
    result: FoldResult,
    *,
    confidence_threshold: float,
    other_mass_threshold: float,
    other_mass: float | None,
) -> bool:
    """REQ-F-INF-009 と REQ-F-BASE-003 の一様フォールバック。"""

    if result.uniform_fallback:
        return True
    if result.top_confidence < confidence_threshold:
        return True
    if other_mass is not None and other_mass > other_mass_threshold:
        return True
    return False


def other_mass_for_model(*, builtin: bool, folded: FoldResult) -> float | None:
    """版 0 は実数、学習済は null（REQ-OBS-007）。"""

    if builtin:
        return float(folded.other_mass)
    return None
