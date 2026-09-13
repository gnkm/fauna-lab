"""Stratified train/val/test assignment (REQ-F-DS-001〜004)."""

from __future__ import annotations

import math
from collections import defaultdict
from random import Random

from faunalab.domain.classes import CLASS_IDS

DEFAULT_TRAIN_RATIO = 0.7
DEFAULT_VAL_RATIO = 0.15
DEFAULT_TEST_RATIO = 0.15
DEFAULT_SEED = 42
RATIO_SUM_TOLERANCE = 1e-9


class RatioError(ValueError):
    """Train/val/test ratios are not a valid partition of 1."""


def validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    for name, value in (
        ("train_ratio", train_ratio),
        ("val_ratio", val_ratio),
        ("test_ratio", test_ratio),
    ):
        if not 0.0 < value < 1.0:
            raise RatioError(f"{name} must be between 0 and 1 exclusive")
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > RATIO_SUM_TOLERANCE:
        raise RatioError("train_ratio + val_ratio + test_ratio must equal 1")


def split_counts(
    n: int, ratios: tuple[float, float, float]
) -> tuple[int, int, int]:
    """Largest-remainder counts so each bucket is within ±1 of n * ratio."""

    if n == 0:
        return (0, 0, 0)
    raw = [ratio * n for ratio in ratios]
    floors = [math.floor(value) for value in raw]
    remainder = n - sum(floors)
    order = sorted(range(3), key=lambda index: (-(raw[index] - floors[index]), index))
    counts = list(floors)
    for index in range(remainder):
        counts[order[index]] += 1
    return counts[0], counts[1], counts[2]


def stratified_assignments(
    labeled: list[tuple[str, str]],
    *,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    val_ratio: float = DEFAULT_VAL_RATIO,
    test_ratio: float = DEFAULT_TEST_RATIO,
    seed: int = DEFAULT_SEED,
) -> dict[str, str]:
    """Map labeled image refs to train/val/test. Unlabeled refs are omitted."""

    validate_ratios(train_ratio, val_ratio, test_ratio)
    by_class: dict[str, list[str]] = defaultdict(list)
    for ref, class_id in labeled:
        by_class[class_id].append(ref)
    rng = Random(seed)
    assignments: dict[str, str] = {}
    ratios = (train_ratio, val_ratio, test_ratio)
    for class_id in CLASS_IDS:
        refs = sorted(by_class.get(class_id, ()))
        rng.shuffle(refs)
        n_train, n_val, _n_test = split_counts(len(refs), ratios)
        for index, ref in enumerate(refs):
            if index < n_train:
                assignments[ref] = "train"
            elif index < n_train + n_val:
                assignments[ref] = "val"
            else:
                assignments[ref] = "test"
    return assignments
