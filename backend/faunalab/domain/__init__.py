"""Invariants and use cases. Must not depend on HTTP."""

from faunalab.domain.classes import CLASS_IDS, SYSTEM_CLASSES, ClassSpec
from faunalab.domain.images import (
    MAX_IMAGE_BYTES,
    MAX_UPLOAD_FILES,
    UnsupportedImageError,
)

__all__ = [
    "CLASS_IDS",
    "MAX_IMAGE_BYTES",
    "MAX_UPLOAD_FILES",
    "SYSTEM_CLASSES",
    "ClassSpec",
    "UnsupportedImageError",
]
