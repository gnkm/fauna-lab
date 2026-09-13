"""Common image preprocessing (REQ-F-BASE-002).

The 5 steps match torchvision's ImageNet eval pipeline
(`Resize(256)` + `CenterCrop(224)` + `ToTensor` + `Normalize`) so that
training, evaluation, and inference share one implementation. The API
process uses Pillow and NumPy and does not import PyTorch
(REQ-PERF-006 / DESIGN I-BASE-001).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image

SHORT_EDGE = 256
CROP_SIZE = 224
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

Float32Array = NDArray[np.float32]


def to_rgb(image: Image.Image) -> Image.Image:
    """Convert to RGB 3 channels. Grayscale is replicated; alpha is dropped."""

    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def resize_short_edge(
    image: Image.Image, short_edge: int = SHORT_EDGE
) -> Image.Image:
    """Resize so the shorter side equals `short_edge`, keeping aspect ratio.

    Uses bilinear interpolation. The integer size follows torchvision:
    `int(short_edge * long / short)` (truncation toward zero).
    """

    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("image has invalid size")
    if width <= height:
        new_w = short_edge
        new_h = int(short_edge * height / width)
    else:
        new_h = short_edge
        new_w = int(short_edge * width / height)
    if (new_w, new_h) == (width, height):
        return image
    return image.resize((new_w, new_h), resample=Image.Resampling.BILINEAR)


def center_crop(image: Image.Image, size: int = CROP_SIZE) -> Image.Image:
    """Crop `size` × `size` from the center (torchvision `int(round(...))`)."""

    width, height = image.size
    if width < size or height < size:
        raise ValueError("image is smaller than the crop size")
    left = int(round((width - size) / 2.0))
    top = int(round((height - size) / 2.0))
    return image.crop((left, top, left + size, top + size))


def to_normalized_nchw(image: Image.Image) -> Float32Array:
    """HWC uint8 RGB → CHW float32 in `[0, 1]`, then ImageNet normalize."""

    arr = np.asarray(image, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("expected RGB image array")
    chw = np.transpose(arr, (2, 0, 1)).astype(np.float32) / 255.0
    mean = IMAGENET_MEAN[:, None, None]
    std = IMAGENET_STD[:, None, None]
    return np.ascontiguousarray((chw - mean) / std, dtype=np.float32)


def preprocess_image(image: Image.Image) -> Float32Array:
    """Apply REQ-F-BASE-002. Returns shape `(3, 224, 224)` float32."""

    rgb = to_rgb(image)
    resized = resize_short_edge(rgb)
    cropped = center_crop(resized)
    return to_normalized_nchw(cropped)


def preprocess_batch(images: Sequence[Image.Image]) -> Float32Array:
    """Stack preprocessed images to `(N, 3, 224, 224)` float32."""

    if not images:
        return np.empty((0, 3, CROP_SIZE, CROP_SIZE), dtype=np.float32)
    return np.stack([preprocess_image(image) for image in images], axis=0)
