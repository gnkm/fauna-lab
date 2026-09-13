"""Image format checks, hashing, and thumbnail generation.

HTTP に依存しない。パス計算に利用者由来のファイル名を使わない
（REQ-ATT-SEC-001、REQ-ATT-SEC-002）。
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageFile, UnidentifiedImageError

ImageFile.LOAD_TRUNCATED_IMAGES = False

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_FILES = 50
THUMB_LONG_EDGE = 256
MAX_ORIGINAL_NAME_CHARS = 1024

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

ImageFormat = Literal["JPEG", "PNG"]


class UnsupportedImageError(Exception):
    """内容が JPEG/PNG として解釈できない（REQ-F-IMG-002、REQ-ATT-REL-003）。"""


@dataclass(frozen=True, slots=True)
class DecodedImage:
    fmt: ImageFormat
    media_type: str
    width: int
    height: int
    thumbnail_jpeg: bytes


def normalize_original_name(name: str | None) -> str:
    """ファイル名は値として保持する。パスには使わない（REQ-ATT-SEC-003）。"""
    raw = name if name is not None else ""
    cleaned = raw.replace("\x00", "").strip()
    if not cleaned:
        return "unnamed"
    if len(cleaned) > MAX_ORIGINAL_NAME_CHARS:
        return cleaned[:MAX_ORIGINAL_NAME_CHARS]
    return cleaned


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_format(data: bytes) -> ImageFormat | None:
    if data.startswith(PNG_MAGIC):
        return "PNG"
    if data.startswith(JPEG_MAGIC):
        return "JPEG"
    return None


def media_type_for(fmt: ImageFormat) -> str:
    return "image/jpeg" if fmt == "JPEG" else "image/png"


def extension_for(fmt: ImageFormat) -> str:
    return ".jpg" if fmt == "JPEG" else ".png"


def image_relpath(sha256: str, fmt: ImageFormat) -> str:
    return f"images/{sha256}{extension_for(fmt)}"


def thumb_relpath(sha256: str) -> str:
    return f"thumbs/{sha256}.jpg"


def media_type_from_path(path: str) -> str | None:
    if path.endswith(".jpg"):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    return None


def decode_and_thumbnail(data: bytes) -> DecodedImage:
    sniffed = sniff_format(data)
    if sniffed is None:
        raise UnsupportedImageError
    try:
        with Image.open(io.BytesIO(data)) as loaded:
            fmt = loaded.format
            if fmt not in {"JPEG", "PNG"}:
                raise UnsupportedImageError
            if fmt != sniffed:
                raise UnsupportedImageError
            loaded.load()
            width, height = loaded.size
            if width <= 0 or height <= 0:
                raise UnsupportedImageError
            thumbnail = _jpeg_thumbnail(loaded)
            return DecodedImage(
                fmt=sniffed,
                media_type=media_type_for(sniffed),
                width=width,
                height=height,
                thumbnail_jpeg=thumbnail,
            )
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise UnsupportedImageError from exc


def _jpeg_thumbnail(source: Image.Image) -> bytes:
    rgb = _to_rgb(source)
    width, height = rgb.size
    longest = max(width, height)
    if longest > THUMB_LONG_EDGE:
        scale = THUMB_LONG_EDGE / longest
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        rgb = rgb.resize(new_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"}:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode == "P":
        converted = image.convert("RGBA")
        background = Image.new("RGB", converted.size, (255, 255, 255))
        background.paste(converted, mask=converted.getchannel("A"))
        return background
    return image.convert("RGB")
