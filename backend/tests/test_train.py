"""NumPy training export matches ONNX Runtime (I-TRN-001 / I-TRN-003)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from faunalab.ml.predict import load_onnx_session
from faunalab.ml.train import (
    EMBEDDING_DIM,
    N_CLASSES,
    _cnn_forward,
    export_cnn_onnx,
    export_linear_onnx,
)


def test_linear_onnx_matches_numpy(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    weight = rng.normal(0, 0.1, size=(N_CLASSES, EMBEDDING_DIM)).astype(np.float32)
    bias = rng.normal(0, 0.1, size=(N_CLASSES,)).astype(np.float32)
    dest = tmp_path / "head.onnx"
    export_linear_onnx(weight, bias, dest)
    session = load_onnx_session(dest)
    inputs = rng.normal(0, 1, size=(4, EMBEDDING_DIM)).astype(np.float32)
    expected = inputs @ weight.T + bias
    name = session.get_inputs()[0].name
    got = np.asarray(session.run(["logits"], {name: inputs})[0], dtype=np.float32)
    np.testing.assert_allclose(got, expected, rtol=1e-5, atol=1e-5)


def test_cnn_onnx_matches_numpy(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    conv1 = rng.normal(0, 0.05, size=(8, 3, 3, 3)).astype(np.float32)
    b1 = np.zeros((8,), dtype=np.float32)
    conv2 = rng.normal(0, 0.05, size=(16, 8, 3, 3)).astype(np.float32)
    b2 = np.zeros((16,), dtype=np.float32)
    fc = rng.normal(0, 0.05, size=(N_CLASSES, 16)).astype(np.float32)
    fcb = np.zeros((N_CLASSES,), dtype=np.float32)
    dest = tmp_path / "cnn.onnx"
    export_cnn_onnx(conv1, b1, conv2, b2, fc, fcb, dest)
    session = load_onnx_session(dest)
    batch = rng.normal(0, 1, size=(2, 3, 224, 224)).astype(np.float32)
    expected, _cache = _cnn_forward(batch, conv1, b1, conv2, b2, fc, fcb)
    name = session.get_inputs()[0].name
    got = np.asarray(session.run(["logits"], {name: batch})[0], dtype=np.float32)
    np.testing.assert_allclose(got, expected, rtol=1e-4, atol=1e-4)
