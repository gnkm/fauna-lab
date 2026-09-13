"""Confusion-matrix metrics (REQ-F-MDL-003 / REQ-OBS-006 / 006a / VER-DATA-004)."""

from __future__ import annotations

from typing import Any

from faunalab.domain.classes import CLASS_IDS
from faunalab.ml.metrics import compute_metrics

METRICS_TOLERANCE = 0.0001

# SRS 附属書 5.3.2（版 2.2）。照合は絶対誤差 0.0001。
ANNEX_EXPECTED: dict[str, Any] = {
    "accuracy": 0.7778,
    "per_class": {
        "samoyed": {
            "precision": 0.8889,
            "recall": 1.0,
            "f1": 0.9412,
            "support": 8,
        },
        "great_pyrenees": {
            "precision": 1.0,
            "recall": 0.8571,
            "f1": 0.9231,
            "support": 7,
        },
        "boxer": {
            "precision": 0.5455,
            "recall": 1.0,
            "f1": 0.7059,
            "support": 6,
        },
        "american_bulldog": {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "support": 5,
        },
        "chihuahua": {
            "precision": 0.8,
            "recall": 1.0,
            "f1": 0.8889,
            "support": 4,
        },
        "miniature_pinscher": {
            "precision": 1.0,
            "recall": 0.6667,
            "f1": 0.8,
            "support": 3,
        },
        "pomeranian": {
            "precision": 0.6667,
            "recall": 1.0,
            "f1": 0.8,
            "support": 2,
        },
        "havanese": {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "support": 1,
        },
    },
    "confusion_matrix": {
        "labels": list(CLASS_IDS),
        "matrix": [
            [8, 0, 0, 0, 0, 0, 0, 0],
            [1, 6, 0, 0, 0, 0, 0, 0],
            [0, 0, 6, 0, 0, 0, 0, 0],
            [0, 0, 5, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 4, 0, 0, 0],
            [0, 0, 0, 0, 1, 2, 0, 0],
            [0, 0, 0, 0, 0, 0, 2, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
        ],
    },
}


def annex_pairs() -> tuple[list[str], list[str]]:
    """附属書 5.3.1 の正解 / 予測ペア（36 件）。"""

    pairs: list[tuple[str, str]] = []
    pairs.extend([("samoyed", "samoyed")] * 8)
    pairs.extend([("great_pyrenees", "great_pyrenees")] * 6)
    pairs.append(("great_pyrenees", "samoyed"))
    pairs.extend([("boxer", "boxer")] * 6)
    pairs.extend([("american_bulldog", "boxer")] * 5)
    pairs.extend([("chihuahua", "chihuahua")] * 4)
    pairs.extend([("miniature_pinscher", "miniature_pinscher")] * 2)
    pairs.append(("miniature_pinscher", "chihuahua"))
    pairs.extend([("pomeranian", "pomeranian")] * 2)
    pairs.append(("havanese", "pomeranian"))
    y_true = [item[0] for item in pairs]
    y_pred = [item[1] for item in pairs]
    return y_true, y_pred


def assert_metrics_close(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    tolerance: float = METRICS_TOLERANCE,
) -> None:
    assert abs(float(actual["accuracy"]) - float(expected["accuracy"])) <= tolerance
    actual_per = actual["per_class"]
    expected_per = expected["per_class"]
    assert set(actual_per) == set(CLASS_IDS)
    assert list(actual["confusion_matrix"]["labels"]) == list(CLASS_IDS)
    for class_id in CLASS_IDS:
        got = actual_per[class_id]
        exp = expected_per[class_id]
        assert got["support"] == exp["support"]
        for key in ("precision", "recall", "f1"):
            assert abs(float(got[key]) - float(exp[key])) <= tolerance, class_id
    assert (
        actual["confusion_matrix"]["matrix"] == expected["confusion_matrix"]["matrix"]
    )


def test_annex_5_3_fixed_input_matches_expected() -> None:
    y_true, y_pred = annex_pairs()
    metrics = compute_metrics(y_true, y_pred)
    assert_metrics_close(metrics, ANNEX_EXPECTED)


def test_ver_f_mdl_001_matrix_identity() -> None:
    """混同行列の総和・対角・labels 順を検算する。"""

    y_true, y_pred = annex_pairs()
    metrics = compute_metrics(y_true, y_pred)
    matrix = metrics["confusion_matrix"]["matrix"]
    total = sum(sum(row) for row in matrix)
    assert total == len(y_true) == 36
    diagonal = sum(matrix[i][i] for i in range(len(CLASS_IDS)))
    assert abs(diagonal / total - metrics["accuracy"]) <= 0.001
    assert metrics["confusion_matrix"]["labels"] == list(CLASS_IDS)


def test_obs_006a_zero_prediction_and_support() -> None:
    metrics = compute_metrics(["samoyed"], ["samoyed"])
    empty = metrics["per_class"]["havanese"]
    assert empty == {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "support": 0,
    }
    never_predicted = metrics["per_class"]["boxer"]
    assert never_predicted["precision"] == 0.0
    assert never_predicted["recall"] == 0.0
    assert never_predicted["f1"] == 0.0
