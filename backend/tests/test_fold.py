"""Baseline fold-in (REQ-F-BASE-003 / 004 / 008)."""

from __future__ import annotations

import numpy as np
import pytest
from faunalab.domain.classes import CLASS_IDS
from faunalab.ml.fold import UNIFORM_CONFIDENCE, fold_logits, softmax

_EMPTY_MAP: dict[str, tuple[int, ...]] = {class_id: () for class_id in CLASS_IDS}
_REALISH_MAP = {
    "samoyed": (258,),
    "great_pyrenees": (257,),
    "boxer": (242,),
    "american_bulldog": (),
    "chihuahua": (151,),
    "miniature_pinscher": (237,),
    "pomeranian": (259,),
    "havanese": (),
}


def _logits(*pairs: tuple[int, float]) -> np.ndarray:
    values = np.full(1000, -40.0, dtype=np.float64)
    for index, logit in pairs:
        values[index] = logit
    return values


def test_fold_sums_mapped_indices_not_max() -> None:
    mapping = dict(_EMPTY_MAP)
    mapping["samoyed"] = (0, 1)
    logits = _logits((0, 0.0), (1, 0.0))
    result = fold_logits(logits, mapping)
    assert result.top_class_id == "samoyed"
    assert result.scores["samoyed"] == pytest.approx(1.0)
    assert result.other_mass == pytest.approx(0.0, abs=1e-6)


def test_unmapped_classes_stay_zero_without_interpolation() -> None:
    result = fold_logits(_logits((258, 8.0)), _REALISH_MAP)
    assert result.scores["american_bulldog"] == 0.0
    assert result.scores["havanese"] == 0.0
    assert result.top_class_id == "samoyed"
    assert result.uniform_fallback is False


def test_scores_sum_to_one_and_other_mass_in_unit_interval() -> None:
    result = fold_logits(_logits((258, 3.0), (242, 1.0), (10, 2.0)), _REALISH_MAP)
    assert sum(result.scores.values()) == pytest.approx(1.0, abs=1e-9)
    assert 0.0 <= result.other_mass <= 1.0
    assert len(result.scores) == 8
    assert set(result.scores) == set(CLASS_IDS)


def test_uniform_fallback_when_mapped_mass_is_tiny() -> None:
    result = fold_logits(_logits((999, 30.0)), _REALISH_MAP)
    assert result.uniform_fallback is True
    assert result.other_mass == pytest.approx(1.0, abs=1e-6)
    for class_id in CLASS_IDS:
        assert result.scores[class_id] == UNIFORM_CONFIDENCE


def test_no_temperature_scaling() -> None:
    logits = _logits((258, 4.0), (242, 1.0))
    result = fold_logits(logits, _REALISH_MAP)
    probs = softmax(logits)
    mass = float(probs[258] + probs[242])
    assert result.scores["samoyed"] == pytest.approx(float(probs[258]) / mass)
    assert result.scores["boxer"] == pytest.approx(float(probs[242]) / mass)


def test_tie_breaks_by_display_order() -> None:
    mapping = dict(_EMPTY_MAP)
    mapping["samoyed"] = (0,)
    mapping["great_pyrenees"] = (1,)
    result = fold_logits(_logits((0, 0.0), (1, 0.0)), mapping)
    assert result.top_class_id == "samoyed"
    assert result.top_confidence == pytest.approx(0.5)
