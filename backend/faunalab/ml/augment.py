"""Train-time augmentation on top of the common preprocess (REQ-F-TRN-015/016).

Validation and test paths keep `preprocess_image` (center crop only).
"""

from __future__ import annotations

from numpy.random import Generator
from PIL import Image

from faunalab.ml.preprocess import (
    CROP_SIZE,
    Float32Array,
    center_crop,
    resize_short_edge,
    to_normalized_nchw,
    to_rgb,
)


def random_crop(image: Image.Image, size: int, rng: Generator, /) -> Image.Image:
    width, height = image.size
    if width < size or height < size:
        raise ValueError("image is smaller than the crop size")
    left = int(rng.integers(0, width - size + 1))
    top = int(rng.integers(0, height - size + 1))
    return image.crop((left, top, left + size, top + size))


def preprocess_train(
    image: Image.Image,
    rng: Generator,
    *,
    augmentation: bool,
) -> Float32Array:
    """RGB → short-edge 256, then either random flip+crop or center crop."""

    rgb = to_rgb(image)
    resized = resize_short_edge(rgb)
    if augmentation:
        flipped = (
            resized.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if bool(rng.random() < 0.5)
            else resized
        )
        cropped = random_crop(flipped, CROP_SIZE, rng)
    else:
        cropped = center_crop(resized)
    return to_normalized_nchw(cropped)
