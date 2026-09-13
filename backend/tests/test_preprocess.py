"""Common preprocessing (REQ-F-BASE-002)."""

from __future__ import annotations

import numpy as np
from faunalab.ml.preprocess import (
    CROP_SIZE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    preprocess_batch,
    preprocess_image,
    resize_short_edge,
)
from PIL import Image


def test_rgb_output_shape_and_dtype() -> None:
    image = Image.new("RGB", (320, 240), (10, 20, 30))
    tensor = preprocess_image(image)
    assert tensor.shape == (3, CROP_SIZE, CROP_SIZE)
    assert tensor.dtype == np.float32


def test_grayscale_is_replicated_to_three_channels() -> None:
    gray = Image.new("L", (300, 300), 128)
    rgb = Image.new("RGB", (300, 300), (128, 128, 128))
    np.testing.assert_allclose(
        preprocess_image(gray), preprocess_image(rgb), atol=1e-6
    )


def test_alpha_channel_is_discarded() -> None:
    rgba = Image.new("RGBA", (300, 300), (10, 20, 30, 0))
    tensor = preprocess_image(rgba)
    expected = preprocess_image(Image.new("RGB", (300, 300), (10, 20, 30)))
    np.testing.assert_allclose(tensor, expected, atol=1e-5)


def test_short_edge_resize_matches_torchvision_int_truncation() -> None:
    image = Image.new("RGB", (100, 250), (0, 0, 0))
    resized = resize_short_edge(image, 256)
    assert resized.size == (256, 640)


def test_solid_black_matches_imagenet_normalized_zeros() -> None:
    image = Image.new("RGB", (400, 400), (0, 0, 0))
    tensor = preprocess_image(image)
    expected = (-IMAGENET_MEAN / IMAGENET_STD).reshape(3, 1, 1)
    np.testing.assert_allclose(
        tensor, np.broadcast_to(expected, tensor.shape), atol=1e-5
    )


def test_preprocess_is_deterministic() -> None:
    image = Image.new("RGB", (180, 220), (40, 80, 120))
    first = preprocess_image(image)
    second = preprocess_image(image)
    np.testing.assert_array_equal(first, second)


def test_preprocess_batch_stacks() -> None:
    images = [
        Image.new("RGB", (256, 256), (i, 0, 0)) for i in (0, 50, 100)
    ]
    batch = preprocess_batch(images)
    assert batch.shape == (3, 3, CROP_SIZE, CROP_SIZE)
    np.testing.assert_array_equal(batch[1], preprocess_image(images[1]))
