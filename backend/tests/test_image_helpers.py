"""Image helpers that do not go through HTTP."""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
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


def test_pixel_limit_is_rejected_before_full_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("faunalab.domain.images.MAX_IMAGE_PIXELS", 100)
    image = Image.new("RGB", (20, 20), (1, 2, 3))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    with pytest.raises(UnsupportedImageError):
        decode_and_thumbnail(buffer.getvalue())


def test_decompression_bomb_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    image = Image.new("RGB", (8, 8), (4, 5, 6))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    payload = buffer.getvalue()

    def boom(self: Image.Image) -> None:
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(Image.Image, "load", boom)
    with pytest.raises(UnsupportedImageError):
        decode_and_thumbnail(payload)


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


def test_write_bytes_survives_parallel_same_path(tmp_path: Path) -> None:
    relative = "images/same.bin"
    payload = b"same-bytes"

    def go() -> Path:
        return write_bytes(tmp_path, relative, payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = [future.result() for future in [pool.submit(go) for _ in range(16)]]
    assert {p.read_bytes() for p in paths} == {payload}
    leftovers = [p for p in (tmp_path / "images").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
