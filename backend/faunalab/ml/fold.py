"""Baseline ImageNet → 8-class fold-in (REQ-F-BASE-003 / 004 / 008)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from faunalab.domain.classes import CLASS_IDS

UNIFORM_MASS_EPS = 1e-6
UNIFORM_CONFIDENCE = 0.125
IMAGENET_CLASS_COUNT = 1000

ClassMap = Mapping[str, Sequence[int]]


@dataclass(frozen=True, slots=True)
class FoldResult:
    scores: dict[str, float]
    other_mass: float
    uniform_fallback: bool
    top_class_id: str
    top_confidence: float


def softmax(logits: NDArray[np.floating]) -> NDArray[np.float64]:
    """Numerically stable softmax. No temperature scaling (REQ-F-BASE-008)."""

    x = np.asarray(logits, dtype=np.float64)
    shifted = x - np.max(x, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


def fold_logits(logits: NDArray[np.floating], class_map: ClassMap) -> FoldResult:
    """Fold 1000-d logits into the 8 system classes.

    Unmapped classes keep s(c)=0; there is no interpolation (REQ-F-BASE-004).
    Renormalization is the only probability adjustment (REQ-F-BASE-008).
    """

    vector = np.asarray(logits, dtype=np.float64)
    if vector.ndim != 1 or vector.shape[0] != IMAGENET_CLASS_COUNT:
        raise ValueError(
            f"logits must have shape ({IMAGENET_CLASS_COUNT},), got {vector.shape}"
        )
    probs = softmax(vector)
    summed: dict[str, float] = {}
    for class_id in CLASS_IDS:
        indices = tuple(class_map.get(class_id, ()))
        if not indices:
            summed[class_id] = 0.0
            continue
        # Sum, never max (REQ-F-BASE-003 step 2).
        summed[class_id] = float(np.sum(probs[list(indices)]))
    mass = float(sum(summed.values()))
    other_mass = 1.0 - mass
    if mass >= UNIFORM_MASS_EPS:
        scores = {class_id: summed[class_id] / mass for class_id in CLASS_IDS}
        uniform = False
    else:
        scores = dict.fromkeys(CLASS_IDS, UNIFORM_CONFIDENCE)
        uniform = True
    top_class_id = CLASS_IDS[0]
    top_confidence = scores[top_class_id]
    for class_id in CLASS_IDS[1:]:
        confidence = scores[class_id]
        if confidence > top_confidence:
            top_class_id = class_id
            top_confidence = confidence
    return FoldResult(
        scores=scores,
        other_mass=other_mass,
        uniform_fallback=uniform,
        top_class_id=top_class_id,
        top_confidence=top_confidence,
    )


TRAINED_LOGIT_COUNT = 8


def fold_trained_logits(logits: NDArray[np.floating]) -> FoldResult:
    """Softmax over 8 system-class logits. other_mass is unused (null at API)."""

    vector = np.asarray(logits, dtype=np.float64).reshape(-1)
    if vector.shape[0] != TRAINED_LOGIT_COUNT:
        raise ValueError(
            f"trained logits must have length {TRAINED_LOGIT_COUNT}, got {vector.shape}"
        )
    probs = softmax(vector)
    scores = {class_id: float(probs[index]) for index, class_id in enumerate(CLASS_IDS)}
    top_class_id = CLASS_IDS[0]
    top_confidence = scores[top_class_id]
    for class_id in CLASS_IDS[1:]:
        confidence = scores[class_id]
        if confidence > top_confidence:
            top_class_id = class_id
            top_confidence = confidence
    return FoldResult(
        scores=scores,
        other_mass=0.0,
        uniform_fallback=False,
        top_class_id=top_class_id,
        top_confidence=top_confidence,
    )
