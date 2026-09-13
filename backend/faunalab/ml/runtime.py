"""ONNX Runtime session for baseline inference (API process, no PyTorch)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from faunalab.ml.fold import FoldResult, fold_logits
from faunalab.ml.preprocess import preprocess_batch
from faunalab.ml.session_cache import LockedOnnxSession

LOGGER = logging.getLogger("faunalab.ml.runtime")


class BaselineRuntime:
    """Thread-safe wrapper around an ONNX InferenceSession for version 0."""

    def __init__(self, model_path: Path, class_map: dict[str, tuple[int, ...]]) -> None:
        self.class_map = class_map
        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        )
        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        output_names = [item.name for item in self._session.get_outputs()]
        if "logits" not in output_names:
            raise ValueError("baseline ONNX output does not include logits")
        self._lock = threading.Lock()

    def locked_session(self) -> LockedOnnxSession:
        return LockedOnnxSession(self._session, self._lock)

    def infer_images(self, images: list[Image.Image]) -> list[FoldResult]:
        if not images:
            return []
        batch = preprocess_batch(images)
        with self._lock:
            raw = self._session.run(["logits"], {self._input_name: batch})[0]
        logits = np.asarray(raw)
        if logits.ndim != 2 or logits.shape[0] != len(images):
            raise RuntimeError(f"unexpected logits shape: {logits.shape}")
        return [fold_logits(row, self.class_map) for row in logits]


def try_load_baseline_runtime(
    model_path: Path | None,
    class_map: dict[str, tuple[int, ...]] | None,
) -> BaselineRuntime | None:
    if model_path is None or class_map is None:
        return None
    try:
        return BaselineRuntime(model_path, class_map)
    except Exception:
        LOGGER.warning("failed to load baseline ONNX session", exc_info=True)
        return None
