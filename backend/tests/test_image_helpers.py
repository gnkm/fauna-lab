"""Image helpers that do not go through HTTP."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from faunalab.domain.images import (
    MAX_ORIGINAL_NAME_CHARS,
    UnsupportedImageError,
    decode_and_thumbnail,
    normalize_original_name,
)
from faunalab.persist.files import resolve_under, write_bytes
from PIL import Image


def test_normalize_original_name_treats_empty_and_long_as_values() -> None:
    assert normalize_original_name(None) == "unnamed"
    assert normalize_original_name("  ") == "unnamed"
    assert len(normalize_original_name("a" * 2000)) == MAX_ORIGINAL_NAME_CHARS
    assert normalize_original_name("ok.jpg") == "ok.jpg"


def test_decode_rejects_unknown_format() -> None:
    with pytest.raises(UnsupportedImageError):
        decode_and_thumbnail(b"GIF89a" + b"\x00" * 20)


def test_rgba_png_thumbnail() -> None:
    image = Image.new("RGBA", (12, 8), (10, 20, 30, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    decoded = decode_and_thumbnail(buffer.getvalue())
    assert decoded.fmt == "PNG"
    thumb = Image.open(io.BytesIO(decoded.thumbnail_jpeg))
    assert thumb.mode == "RGB"


def test_palette_png_thumbnail() -> None:
    image = Image.new("P", (10, 10))
    image.putpalette([i % 256 for i in range(768)])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    decoded = decode_and_thumbnail(buffer.getvalue())
    assert decoded.fmt == "PNG"
    assert decoded.width == 10
    thumb = Image.open(io.BytesIO(decoded.thumbnail_jpeg))
    assert thumb.format == "JPEG"


def test_write_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_under(tmp_path, "../secret")
    with pytest.raises(ValueError):
        resolve_under(tmp_path, "/etc/passwd")
    path = write_bytes(tmp_path, "images/ok.bin", b"abc")
    assert path.is_relative_to(tmp_path.resolve())
    assert path.read_bytes() == b"abc"
