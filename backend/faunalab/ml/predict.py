"""Run a persisted ONNX model on images (evaluation / later inference)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from PIL import Image

from faunalab.domain.classes import CLASS_IDS
from faunalab.ml.fold import fold_logits
from faunalab.ml.preprocess import preprocess_image

TRAINED_LOGIT_COUNT = 8
_BATCH_SIZE = 32
ClassMap = Mapping[str, Sequence[int]]


def load_onnx_session(model_path: Path) -> ort.InferenceSession:
    """Load ONNX with CPU only (execution-stage network is forbidden)."""

    return ort.InferenceSession(
        str(model_path),
        providers=["CPUExecutionProvider"],
    )


def predict_class_ids(
    session: ort.InferenceSession,
    image_paths: Sequence[Path],
    *,
    builtin: bool,
    class_map: ClassMap | None = None,
) -> list[str]:
    """Return the top system class for each image, in input order."""

    if builtin and class_map is None:
        raise ValueError("builtin prediction requires class_map")
    predicted: list[str] = []
    for start in range(0, len(image_paths), _BATCH_SIZE):
        chunk = image_paths[start : start + _BATCH_SIZE]
        batch = _load_batch(chunk)
        logits = _run_logits(session, batch)
        for vector in logits:
            if builtin:
                assert class_map is not None
                predicted.append(fold_logits(vector, class_map).top_class_id)
            else:
                predicted.append(_top_trained_class(vector))
    return predicted


def _load_batch(paths: Sequence[Path]) -> NDArray[np.float32]:
    tensors: list[NDArray[np.float32]] = []
    for path in paths:
        with Image.open(path) as image:
            image.load()
            tensors.append(preprocess_image(image))
    return np.stack(tensors, axis=0)


def _run_logits(
    session: ort.InferenceSession, batch: NDArray[np.float32]
) -> NDArray[np.floating]:
    input_name = session.get_inputs()[0].name
    output_names = [item.name for item in session.get_outputs()]
    requested = "logits" if "logits" in output_names else output_names[0]
    raw = session.run([requested], {input_name: batch})[0]
    return np.asarray(raw)


def _top_trained_class(logits: NDArray[np.floating]) -> str:
    """Argmax over 8 logits. Ties keep the smaller display_order (I-OBS-001)."""

    vector = np.asarray(logits, dtype=np.float64).reshape(-1)
    if vector.shape[0] != TRAINED_LOGIT_COUNT:
        raise ValueError(
            f"trained logits must have length {TRAINED_LOGIT_COUNT}, got {vector.shape}"
        )
    best_index = 0
    best_value = float(vector[0])
    for index in range(1, TRAINED_LOGIT_COUNT):
        value = float(vector[index])
        if value > best_value:
            best_index = index
            best_value = value
    return CLASS_IDS[best_index]
