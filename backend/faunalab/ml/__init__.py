"""Preprocessing, baseline fold-in, training, evaluation, ONNX export.

Must not import FastAPI.
"""

from faunalab.ml.baseline import (
    BaselineInspection,
    inspect_baseline_assets,
    load_class_map,
    register_baseline_model,
)
from faunalab.ml.fold import FoldResult, fold_logits, softmax
from faunalab.ml.metrics import compute_metrics
from faunalab.ml.predict import load_onnx_session, predict_class_ids
from faunalab.ml.preprocess import preprocess_batch, preprocess_image
from faunalab.ml.runtime import BaselineRuntime, try_load_baseline_runtime

__all__ = [
    "BaselineInspection",
    "BaselineRuntime",
    "FoldResult",
    "compute_metrics",
    "fold_logits",
    "inspect_baseline_assets",
    "load_class_map",
    "load_onnx_session",
    "predict_class_ids",
    "preprocess_batch",
    "preprocess_image",
    "register_baseline_model",
    "softmax",
    "try_load_baseline_runtime",
]
