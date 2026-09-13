"""Score a trained ONNX model (image CNN or embedding head). No PyTorch."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from PIL import Image

from faunalab.ml.embeddings import extract_embeddings
from faunalab.ml.fold import FoldResult, fold_trained_logits
from faunalab.ml.predict import load_onnx_session
from faunalab.ml.preprocess import preprocess_batch

_BATCH = 32


def is_embedding_head(session: ort.InferenceSession) -> bool:
    shape = session.get_inputs()[0].shape
    dims = [item for item in shape if isinstance(item, int) and item > 0]
    return 1280 in dims and 3 not in dims


def infer_trained_images(
    session: ort.InferenceSession,
    images: Sequence[Image.Image],
    *,
    embedding_session: ort.InferenceSession | None = None,
) -> list[FoldResult]:
    if not images:
        return []
    logits = _logits_for_images(session, images, embedding_session=embedding_session)
    return [fold_trained_logits(row) for row in logits]


def infer_trained_paths(
    session: ort.InferenceSession,
    image_paths: Sequence[Path],
    *,
    embedding_session: ort.InferenceSession | None = None,
) -> list[str]:
    images: list[Image.Image] = []
    try:
        for path in image_paths:
            with Image.open(path) as image:
                image.load()
                images.append(image.copy())
        folded = infer_trained_images(
            session, images, embedding_session=embedding_session
        )
    finally:
        for image in images:
            image.close()
    return [item.top_class_id for item in folded]


def _logits_for_images(
    session: ort.InferenceSession,
    images: Sequence[Image.Image],
    *,
    embedding_session: ort.InferenceSession | None,
) -> NDArray[np.floating]:
    if is_embedding_head(session):
        if embedding_session is None:
            raise ValueError("embedding-head ONNX requires a baseline session")
        chunks: list[NDArray[np.floating]] = []
        for start in range(0, len(images), _BATCH):
            piece = list(images[start : start + _BATCH])
            embeddings = extract_embeddings(embedding_session, piece)
            chunks.append(_run_head(session, embeddings))
        return np.concatenate(chunks, axis=0)
    chunks = []
    for start in range(0, len(images), _BATCH):
        piece = list(images[start : start + _BATCH])
        batch = preprocess_batch(piece)
        chunks.append(_run_head(session, batch))
    return np.concatenate(chunks, axis=0)


def _run_head(
    session: ort.InferenceSession, inputs: NDArray[np.floating]
) -> NDArray[np.floating]:
    input_name = session.get_inputs()[0].name
    output_names = [item.name for item in session.get_outputs()]
    requested = "logits" if "logits" in output_names else output_names[0]
    raw = session.run([requested], {input_name: np.asarray(inputs, dtype=np.float32)})[
        0
    ]
    return np.asarray(raw)


def load_trained_session(model_path: Path) -> ort.InferenceSession:
    return load_onnx_session(model_path)
