"""ONNX session cache reuses loaded models (I-TRN-005)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
from faunalab.ml.predict import load_onnx_session
from faunalab.ml.session_cache import OnnxSessionCache
from faunalab.ml.train import N_CLASSES, export_cnn_onnx


def _cnn_onnx(dest: Path) -> Path:
    rng = np.random.default_rng(5)
    export_cnn_onnx(
        rng.normal(0, 0.05, size=(8, 3, 3, 3)).astype(np.float32),
        np.zeros((8,), dtype=np.float32),
        rng.normal(0, 0.05, size=(16, 8, 3, 3)).astype(np.float32),
        np.zeros((16,), dtype=np.float32),
        rng.normal(0, 0.05, size=(N_CLASSES, 16)).astype(np.float32),
        np.zeros((N_CLASSES,), dtype=np.float32),
        dest,
    )
    return dest


def test_cache_returns_same_session(tmp_path: Path) -> None:
    dest = _cnn_onnx(tmp_path / "model.onnx")
    cache = OnnxSessionCache()
    with patch(
        "faunalab.ml.session_cache.load_onnx_session", wraps=load_onnx_session
    ) as spy:
        first = cache.get(dest)
        second = cache.get(dest)
        assert first is second
        assert spy.call_count == 1


def test_cache_reloads_when_file_changes(tmp_path: Path) -> None:
    dest = _cnn_onnx(tmp_path / "model.onnx")
    cache = OnnxSessionCache()
    first = cache.get(dest)
    stat = dest.stat()
    os.utime(dest, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    with patch(
        "faunalab.ml.session_cache.load_onnx_session", wraps=load_onnx_session
    ) as spy:
        second = cache.get(dest)
        assert spy.call_count == 1
    assert first is not second


def test_cache_evicts_previous_trained_session(tmp_path: Path) -> None:
    first_path = _cnn_onnx(tmp_path / "v1.onnx")
    second_path = _cnn_onnx(tmp_path / "v2.onnx")
    cache = OnnxSessionCache()
    kept = cache.get(first_path)
    cache.get(second_path)
    with patch(
        "faunalab.ml.session_cache.load_onnx_session", wraps=load_onnx_session
    ) as spy:
        reloaded = cache.get(first_path)
        assert spy.call_count == 1
    assert reloaded is not kept
