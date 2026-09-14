"""CPU training loops implemented in NumPy. The worker imports this module.

PyTorch's PyPI wheels pull NVIDIA CUDA redistributables (not OSI), and the
CPU wheel index is not reachable at lock time. The algorithm still matches
ARCHITECTURE: frozen embedding + linear head, or a tiny CNN (I-TRN-003).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import onnx
from numpy.random import Generator
from numpy.typing import NDArray
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from faunalab.domain.classes import CLASS_IDS
from faunalab.domain.jobs import JobCanceled, JobParams
from faunalab.ml.augment import preprocess_train
from faunalab.ml.embeddings import extract_embeddings_nchw, load_embedding_session
from faunalab.ml.preprocess import preprocess_image

N_CLASSES = len(CLASS_IDS)
EMBEDDING_DIM = 1280
Float32 = NDArray[np.float32]


class Adam:
    def __init__(
        self,
        params: list[Float32],
        *,
        lr: float,
        betas: tuple[float, float] = (0.9, 0.999),
        eps: float = 1e-8,
    ) -> None:
        self.params = params
        self.lr = lr
        self.betas = betas
        self.eps = eps
        self.m = [np.zeros_like(item) for item in params]
        self.v = [np.zeros_like(item) for item in params]
        self.t = 0

    def step(self, grads: list[Float32]) -> None:
        self.t += 1
        b1, b2 = self.betas
        for index, (param, grad) in enumerate(zip(self.params, grads, strict=True)):
            self.m[index] = (b1 * self.m[index] + (1.0 - b1) * grad).astype(np.float32)
            self.v[index] = (b2 * self.v[index] + (1.0 - b2) * (grad * grad)).astype(
                np.float32
            )
            m_hat = self.m[index] / (1.0 - b1**self.t)
            v_hat = self.v[index] / (1.0 - b2**self.t)
            param -= (self.lr * m_hat / (np.sqrt(v_hat) + self.eps)).astype(np.float32)


def seed_all(seed: int) -> Generator:
    np.random.seed(seed)
    return np.random.default_rng(seed)


def softmax_cross_entropy(
    logits: Float32, targets: NDArray[np.int64]
) -> tuple[float, Float32]:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    probs = exp / exp.sum(axis=1, keepdims=True)
    n = logits.shape[0]
    picked = probs[np.arange(n), targets]
    loss = float(-np.log(np.clip(picked, 1e-12, 1.0)).mean())
    grad = probs
    grad[np.arange(n), targets] -= 1.0
    grad /= n
    return loss, grad.astype(np.float32)


def accuracy_from_logits(logits: Float32, targets: NDArray[np.int64]) -> float:
    predicted = np.argmax(logits, axis=1)
    return float((predicted == targets).mean())


def class_index(class_id: str) -> int:
    return CLASS_IDS.index(class_id)


def train_baseline_head(
    *,
    train_images: list[Image.Image],
    train_labels: list[str],
    val_images: list[Image.Image],
    val_labels: list[str],
    params: JobParams,
    baseline_path: Path,
    dest: Path,
    should_cancel: Callable[[], bool],
    on_epoch: Callable[[int, float, float, float, float], None],
) -> None:
    rng = seed_all(params.seed)
    session = load_embedding_session(baseline_path)
    weight = rng.normal(0.0, 0.02, size=(N_CLASSES, EMBEDDING_DIM)).astype(np.float32)
    bias = np.zeros((N_CLASSES,), dtype=np.float32)
    optimizer = Adam([weight, bias], lr=params.learning_rate)
    train_y = np.array([class_index(item) for item in train_labels], dtype=np.int64)
    val_y = np.array([class_index(item) for item in val_labels], dtype=np.int64)
    n_train = len(train_images)
    for epoch in range(1, params.epochs + 1):
        if should_cancel():
            raise JobCanceled
        started = time.perf_counter()
        order = rng.permutation(n_train)
        total_loss = 0.0
        seen = 0
        for start in range(0, n_train, params.batch_size):
            if should_cancel():
                raise JobCanceled
            index = order[start : start + params.batch_size]
            batch = np.stack(
                [
                    preprocess_train(
                        train_images[int(i)], rng, augmentation=params.augmentation
                    )
                    for i in index
                ]
            )
            embeddings = extract_embeddings_nchw(session, batch)
            logits = embeddings @ weight.T + bias
            loss, grad_logits = softmax_cross_entropy(logits, train_y[index])
            grad_w = grad_logits.T @ embeddings
            grad_b = grad_logits.sum(axis=0)
            optimizer.step([grad_w.astype(np.float32), grad_b.astype(np.float32)])
            total_loss += loss * int(index.shape[0])
            seen += int(index.shape[0])
        train_loss = total_loss / max(seen, 1)
        val_loss, val_accuracy = _eval_head(
            session, weight, bias, val_images, val_y, should_cancel
        )
        elapsed = time.perf_counter() - started
        on_epoch(epoch, train_loss, val_loss, val_accuracy, elapsed)
    export_linear_onnx(weight, bias, dest)


def train_tiny_cnn(
    *,
    train_images: list[Image.Image],
    train_labels: list[str],
    val_images: list[Image.Image],
    val_labels: list[str],
    params: JobParams,
    dest: Path,
    should_cancel: Callable[[], bool],
    on_epoch: Callable[[int, float, float, float, float], None],
) -> None:
    rng = seed_all(params.seed)
    conv1 = rng.normal(0.0, 0.05, size=(8, 3, 3, 3)).astype(np.float32)
    b1 = np.zeros((8,), dtype=np.float32)
    conv2 = rng.normal(0.0, 0.05, size=(16, 8, 3, 3)).astype(np.float32)
    b2 = np.zeros((16,), dtype=np.float32)
    fc = rng.normal(0.0, 0.05, size=(N_CLASSES, 16)).astype(np.float32)
    fcb = np.zeros((N_CLASSES,), dtype=np.float32)
    optimizer = Adam([conv1, b1, conv2, b2, fc, fcb], lr=params.learning_rate)
    train_y = np.array([class_index(item) for item in train_labels], dtype=np.int64)
    val_y = np.array([class_index(item) for item in val_labels], dtype=np.int64)
    n_train = len(train_images)
    for epoch in range(1, params.epochs + 1):
        if should_cancel():
            raise JobCanceled
        started = time.perf_counter()
        order = rng.permutation(n_train)
        total_loss = 0.0
        seen = 0
        for start in range(0, n_train, params.batch_size):
            if should_cancel():
                raise JobCanceled
            index = order[start : start + params.batch_size]
            batch = np.stack(
                [
                    preprocess_train(
                        train_images[int(i)], rng, augmentation=params.augmentation
                    )
                    for i in index
                ]
            )
            logits, cache = _cnn_forward(batch, conv1, b1, conv2, b2, fc, fcb)
            loss, grad_logits = softmax_cross_entropy(logits, train_y[index])
            grads = _cnn_backward(grad_logits, cache)
            optimizer.step(grads)
            total_loss += loss * int(index.shape[0])
            seen += int(index.shape[0])
        train_loss = total_loss / max(seen, 1)
        val_loss, val_accuracy = _eval_cnn(
            conv1, b1, conv2, b2, fc, fcb, val_images, val_y, should_cancel
        )
        elapsed = time.perf_counter() - started
        on_epoch(epoch, train_loss, val_loss, val_accuracy, elapsed)
    export_cnn_onnx(conv1, b1, conv2, b2, fc, fcb, dest)


def _eval_head(
    session,
    weight: Float32,
    bias: Float32,
    images: list[Image.Image],
    targets: NDArray[np.int64],
    should_cancel: Callable[[], bool],
) -> tuple[float, float]:
    if should_cancel():
        raise JobCanceled
    batch = np.stack([preprocess_image(image) for image in images])
    embeddings = extract_embeddings_nchw(session, batch)
    logits = embeddings @ weight.T + bias
    loss, _grad = softmax_cross_entropy(logits, targets)
    return loss, accuracy_from_logits(logits, targets)


def _eval_cnn(
    conv1: Float32,
    b1: Float32,
    conv2: Float32,
    b2: Float32,
    fc: Float32,
    fcb: Float32,
    images: list[Image.Image],
    targets: NDArray[np.int64],
    should_cancel: Callable[[], bool],
) -> tuple[float, float]:
    if should_cancel():
        raise JobCanceled
    batch = np.stack([preprocess_image(image) for image in images])
    logits, _cache = _cnn_forward(batch, conv1, b1, conv2, b2, fc, fcb)
    loss, _grad = softmax_cross_entropy(logits, targets)
    return loss, accuracy_from_logits(logits, targets)


def _conv_forward(
    inputs: Float32, weight: Float32, bias: Float32, stride: int
) -> tuple[Float32, tuple[Float32, Float32, Float32, int, tuple[int, int]]]:
    n, _c, height, width = inputs.shape
    out_c, _in_c, k_h, k_w = weight.shape
    out_h = (height - k_h) // stride + 1
    out_w = (width - k_w) // stride + 1
    cols = _im2col(inputs, k_h, k_w, stride)
    w_flat = weight.reshape(out_c, -1)
    out = (w_flat @ cols).reshape(out_c, n, out_h, out_w).transpose(1, 0, 2, 3)
    out = out + bias.reshape(1, out_c, 1, 1)
    return out.astype(np.float32), (inputs, weight, cols, stride, (out_h, out_w))


def _conv_backward(
    grad: Float32,
    cache: tuple[Float32, Float32, Float32, int, tuple[int, int]],
) -> tuple[Float32, Float32, Float32]:
    inputs, weight, cols, stride, (out_h, out_w) = cache
    n, out_c, _oh, _ow = grad.shape
    grad_flat = grad.transpose(1, 0, 2, 3).reshape(out_c, -1)
    w_flat = weight.reshape(out_c, -1)
    grad_w = (grad_flat @ cols.T).reshape(weight.shape)
    grad_b = grad.sum(axis=(0, 2, 3))
    grad_cols = w_flat.T @ grad_flat
    grad_in = _col2im(grad_cols, inputs.shape, weight.shape[2], weight.shape[3], stride)
    return (
        grad_in.astype(np.float32),
        grad_w.astype(np.float32),
        grad_b.astype(np.float32),
    )


def _im2col(inputs: Float32, k_h: int, k_w: int, stride: int) -> Float32:
    array = np.ascontiguousarray(inputs, dtype=np.float32)
    n, channels, height, width = array.shape
    out_h = (height - k_h) // stride + 1
    out_w = (width - k_w) // stride + 1
    stride_n, stride_c, stride_h, stride_w = array.strides
    patches = np.lib.stride_tricks.as_strided(
        array,
        shape=(n, channels, out_h, out_w, k_h, k_w),
        strides=(
            stride_n,
            stride_c,
            stride_h * stride,
            stride_w * stride,
            stride_h,
            stride_w,
        ),
        writeable=False,
    )
    return np.ascontiguousarray(
        patches.transpose(1, 4, 5, 0, 2, 3).reshape(
            channels * k_h * k_w, n * out_h * out_w
        )
    )


def _col2im(
    cols: Float32,
    shape: tuple[int, ...],
    k_h: int,
    k_w: int,
    stride: int,
) -> Float32:
    n, channels, height, width = shape
    out_h = (height - k_h) // stride + 1
    out_w = (width - k_w) // stride + 1
    result = np.zeros(shape, dtype=np.float32)
    cols_6d = cols.reshape(channels, k_h, k_w, n, out_h, out_w)
    for out_row in range(out_h):
        top = out_row * stride
        for out_col in range(out_w):
            left = out_col * stride
            patch = cols_6d[:, :, :, :, out_row, out_col].transpose(3, 0, 1, 2)
            result[:, :, top : top + k_h, left : left + k_w] += patch
    return result


def _relu(values: Float32) -> tuple[Float32, Float32]:
    mask = (values > 0).astype(np.float32)
    return values * mask, mask


def _cnn_forward(
    batch: Float32,
    conv1: Float32,
    b1: Float32,
    conv2: Float32,
    b2: Float32,
    fc: Float32,
    fcb: Float32,
) -> tuple[Float32, dict[str, object]]:
    h1, cache1 = _conv_forward(batch, conv1, b1, stride=8)
    r1, mask1 = _relu(h1)
    h2, cache2 = _conv_forward(r1, conv2, b2, stride=4)
    r2, mask2 = _relu(h2)
    pooled = r2.mean(axis=(2, 3))
    logits = pooled @ fc.T + fcb
    cache = {
        "cache1": cache1,
        "cache2": cache2,
        "mask1": mask1,
        "mask2": mask2,
        "r2": r2,
        "pooled": pooled,
        "fc": fc,
    }
    return logits.astype(np.float32), cache


def _cnn_backward(grad_logits: Float32, cache: dict[str, object]) -> list[Float32]:
    pooled = cache["pooled"]
    fc = cache["fc"]
    r2 = cache["r2"]
    assert isinstance(pooled, np.ndarray)
    assert isinstance(fc, np.ndarray)
    assert isinstance(r2, np.ndarray)
    grad_fc = grad_logits.T @ pooled
    grad_fcb = grad_logits.sum(axis=0)
    grad_pooled = grad_logits @ fc
    n, channels, height, width = r2.shape
    grad_r2 = grad_pooled.reshape(n, channels, 1, 1) / float(height * width)
    mask2 = cache["mask2"]
    assert isinstance(mask2, np.ndarray)
    grad_h2 = grad_r2 * mask2
    cache2 = cache["cache2"]
    assert isinstance(cache2, tuple)
    grad_r1, grad_conv2, grad_b2 = _conv_backward(grad_h2.astype(np.float32), cache2)
    mask1 = cache["mask1"]
    assert isinstance(mask1, np.ndarray)
    grad_h1 = grad_r1 * mask1
    cache1 = cache["cache1"]
    assert isinstance(cache1, tuple)
    _grad_in, grad_conv1, grad_b1 = _conv_backward(grad_h1.astype(np.float32), cache1)
    return [
        grad_conv1.astype(np.float32),
        grad_b1.astype(np.float32),
        grad_conv2.astype(np.float32),
        grad_b2.astype(np.float32),
        grad_fc.astype(np.float32),
        grad_fcb.astype(np.float32),
    ]


def export_linear_onnx(weight: Float32, bias: Float32, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    w_init = numpy_helper.from_array(weight.astype(np.float32), name="W")
    b_init = numpy_helper.from_array(bias.astype(np.float32), name="B")
    node = helper.make_node("Gemm", ["input", "W", "B"], ["logits"], transB=1)
    graph = helper.make_graph(
        [node],
        "linear_head",
        [
            helper.make_tensor_value_info(
                "input", TensorProto.FLOAT, ["N", EMBEDDING_DIM]
            )
        ],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", N_CLASSES])],
        [w_init, b_init],
    )
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 13)],
        ir_version=8,
    )
    onnx.save(model, str(dest))


def export_cnn_onnx(
    conv1: Float32,
    b1: Float32,
    conv2: Float32,
    b2: Float32,
    fc: Float32,
    fcb: Float32,
    dest: Path,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    initializers = [
        numpy_helper.from_array(conv1, name="conv1_w"),
        numpy_helper.from_array(b1, name="conv1_b"),
        numpy_helper.from_array(conv2, name="conv2_w"),
        numpy_helper.from_array(b2, name="conv2_b"),
        numpy_helper.from_array(fc, name="fc_w"),
        numpy_helper.from_array(fcb, name="fc_b"),
    ]
    nodes = [
        helper.make_node(
            "Conv",
            ["input", "conv1_w", "conv1_b"],
            ["h1"],
            kernel_shape=[3, 3],
            strides=[8, 8],
        ),
        helper.make_node("Relu", ["h1"], ["r1"]),
        helper.make_node(
            "Conv",
            ["r1", "conv2_w", "conv2_b"],
            ["h2"],
            kernel_shape=[3, 3],
            strides=[4, 4],
        ),
        helper.make_node("Relu", ["h2"], ["r2"]),
        helper.make_node("GlobalAveragePool", ["r2"], ["pool"]),
        helper.make_node("Flatten", ["pool"], ["flat"], axis=1),
        helper.make_node("Gemm", ["flat", "fc_w", "fc_b"], ["logits"], transB=1),
    ]
    graph = helper.make_graph(
        nodes,
        "tiny_cnn",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["N", 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", N_CLASSES])],
        initializers,
    )
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 13)],
        ir_version=8,
    )
    onnx.save(model, str(dest))
