"""Frozen baseline embeddings via ONNX Runtime (no PyTorch)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from PIL import Image

from faunalab.ml.predict import load_onnx_session
from faunalab.ml.preprocess import preprocess_image
from faunalab.ml.session_cache import OnnxRunnable

EMBEDDING_DIM = 1280
Float32Array = NDArray[np.float32]


def embedding_output_name(session: OnnxRunnable) -> str:
    names = [item.name for item in session.get_outputs()]
    if "embedding" in names:
        return "embedding"
    raise ValueError("baseline ONNX output does not include embedding")


def extract_embeddings(
    session: OnnxRunnable,
    images: list[Image.Image],
) -> Float32Array:
    """Return shape `(N, 1280)` float32 in input order (eval preprocess)."""

    if not images:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
    batch = np.stack([preprocess_image(image) for image in images], axis=0)
    return extract_embeddings_nchw(session, batch)


def extract_embeddings_nchw(
    session: OnnxRunnable,
    batch: Float32Array,
) -> Float32Array:
    """Run embedding on an already-preprocessed `(N, 3, 224, 224)` batch."""

    if batch.shape[0] == 0:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
    input_name = session.get_inputs()[0].name
    output_name = embedding_output_name(session)
    rows: list[NDArray[np.float32]] = []
    for index in range(batch.shape[0]):
        piece = np.expand_dims(batch[index], axis=0)
        raw = session.run([output_name], {input_name: piece})[0]
        vector = np.asarray(raw, dtype=np.float32).reshape(-1)
        if vector.shape[0] != EMBEDDING_DIM:
            raise RuntimeError(
                f"unexpected embedding dim {vector.shape}, expected {EMBEDDING_DIM}"
            )
        rows.append(vector)
    return np.stack(rows, axis=0)


def load_embedding_session(model_path: Path) -> ort.InferenceSession:
    return load_onnx_session(model_path)
