"""Evaluation metrics (REQ-F-MDL-003 / REQ-OBS-006 / REQ-OBS-006a)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from faunalab.domain.classes import CLASS_IDS

Metrics = dict[str, Any]


def compute_metrics(y_true: Sequence[str], y_pred: Sequence[str]) -> Metrics:
    """Build accuracy, per-class scores, and the 8×8 confusion matrix.

    `matrix[i][j]` is true `labels[i]` predicted as `labels[j]`.
    Labels follow `display_order`. Zero-count classes use REQ-OBS-006a:
    predicted 0 → precision 0, true 0 → recall 0, both 0 → F1 0.
    """

    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if not y_true:
        raise ValueError("metrics require at least one pair")
    index = {class_id: i for i, class_id in enumerate(CLASS_IDS)}
    size = len(CLASS_IDS)
    matrix = [[0 for _ in range(size)] for _ in range(size)]
    for true_id, pred_id in zip(y_true, y_pred, strict=True):
        if true_id not in index:
            raise ValueError(f"unknown true class {true_id!r}")
        if pred_id not in index:
            raise ValueError(f"unknown predicted class {pred_id!r}")
        matrix[index[true_id]][index[pred_id]] += 1
    total = len(y_true)
    diagonal = sum(matrix[i][i] for i in range(size))
    per_class: dict[str, dict[str, float | int]] = {}
    for i, class_id in enumerate(CLASS_IDS):
        true_positive = matrix[i][i]
        support = sum(matrix[i])
        predicted = sum(matrix[row][i] for row in range(size))
        precision = 0.0 if predicted == 0 else true_positive / predicted
        recall = 0.0 if support == 0 else true_positive / support
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2.0 * precision * recall / (precision + recall)
        per_class[class_id] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
    return {
        "accuracy": diagonal / total,
        "per_class": per_class,
        "confusion_matrix": {
            "labels": list(CLASS_IDS),
            "matrix": matrix,
        },
    }
