"""Stratified split counts (REQ-F-DS-002)."""

from __future__ import annotations

from faunalab.domain.classes import CLASS_IDS
from faunalab.domain.splits import RatioError, split_counts, stratified_assignments


def test_split_counts_within_one_of_expected() -> None:
    for n in (0, 1, 2, 7, 8, 10, 100):
        counts = split_counts(n, (0.7, 0.15, 0.15))
        assert sum(counts) == n
        for count, ratio in zip(counts, (0.7, 0.15, 0.15), strict=True):
            assert abs(count - ratio * n) <= 1


def test_assignments_are_deterministic() -> None:
    labeled = [
        (f"{class_id}-{index:03d}", class_id)
        for class_id in CLASS_IDS
        for index in range(10)
    ]
    first = stratified_assignments(labeled, seed=42)
    second = stratified_assignments(labeled, seed=42)
    third = stratified_assignments(labeled, seed=7)
    assert first == second
    assert first != third


def test_invalid_ratio_sum_is_rejected() -> None:
    try:
        stratified_assignments(
            [("a", "samoyed")], train_ratio=0.5, val_ratio=0.5, test_ratio=0.5
        )
    except RatioError:
        return
    raise AssertionError("expected RatioError")
