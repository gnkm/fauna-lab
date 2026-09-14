"""Train-time augmentation stays off the val/test preprocess path."""

from __future__ import annotations

import numpy as np
from faunalab.ml.augment import preprocess_train, random_crop
from faunalab.ml.preprocess import CROP_SIZE, preprocess_image
from PIL import Image


def test_random_crop_is_square() -> None:
    image = Image.new("RGB", (300, 280), (10, 20, 30))
    rng = np.random.default_rng(0)
    cropped = random_crop(image, CROP_SIZE, rng)
    assert cropped.size == (CROP_SIZE, CROP_SIZE)


def test_train_without_aug_matches_eval_preprocess() -> None:
    image = Image.new("RGB", (80, 60), (40, 50, 60))
    rng = np.random.default_rng(1)
    train = preprocess_train(image, rng, augmentation=False)
    eval_tensor = preprocess_image(image)
    assert train.shape == eval_tensor.shape
    assert np.allclose(train, eval_tensor)


def test_train_aug_changes_tensor() -> None:
    image = Image.new("RGB", (80, 60), (1, 2, 3))
    image.putpixel((10, 10), (255, 0, 0))
    image.putpixel((50, 20), (0, 255, 0))
    rng = np.random.default_rng(7)
    augmented = preprocess_train(image, rng, augmentation=True)
    eval_tensor = preprocess_image(image)
    assert augmented.shape == eval_tensor.shape
    assert not np.allclose(augmented, eval_tensor)
