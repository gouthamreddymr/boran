"""The .brn file: one shareable file holding a photo plus the names of the people in it.

Layout (big-endian):
    8s  magic          b"BORAN\\x89\\r\\n"
    H   version
    I   header length  (JSON, UTF-8)
    Q   image length
    ... header JSON    (image name, size, SHA-256 of the image, faces, optional edits)
    ... image bytes    (the original JPEG/PNG/... file, untouched; edits never change it, so they can always be undone)
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from boran.models import FaceBox

SUFFIX = ".brn"
VERSION = 1
MAX_HEADER_BYTES = 32 * 1024 * 1024
MAX_IMAGE_BYTES = 1024 * 1024 * 1024
_MAGIC = b"BORAN\x89\r\n"
_PREFIX = struct.Struct(">8sHIQ")


class BrnError(Exception):
    pass


@dataclass
class BrnFile:
    image_bytes: bytes
    image_name: str
    size: tuple[int, int]
    faces: list[FaceBox]
    edits: dict | None = None  # raw edit settings; see boran.edits.Edits.from_dict


def write_brn(
    path: Path, image_bytes: bytes, image_name: str, size: tuple[int, int], faces: list[FaceBox],
    edits: dict | None = None,
) -> None:
    """Atomically write a .brn file."""
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise BrnError("Image is empty or too large to share")
    fields = {
        "app": "boran",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "image_name": Path(image_name).name[:255],
        "width": size[0],
        "height": size[1],
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "faces": [f.to_dict() for f in faces],
    }
    if edits:
        fields["edits"] = edits
    header = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
            tmp_name = tmp.name
            tmp.write(_PREFIX.pack(_MAGIC, VERSION, len(header), len(image_bytes)))
            tmp.write(header)
            tmp.write(image_bytes)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
    except OSError as exc:
        raise BrnError(f"Cannot write {path.name}: {exc}") from exc
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def read_brn(path: Path) -> BrnFile:
    """Read and fully validate a .brn file; raises BrnError if anything is wrong."""
    try:
        with open(path, "rb") as fh:
            prefix = fh.read(_PREFIX.size)
            if len(prefix) != _PREFIX.size:
                raise BrnError("File is too short to be a Boran file")
            magic, version, header_len, image_len = _PREFIX.unpack(prefix)
            if magic != _MAGIC:
                raise BrnError("Not a Boran file")
            if version > VERSION:
                raise BrnError("This file was made by a newer version of the app")
            if header_len > MAX_HEADER_BYTES or image_len > MAX_IMAGE_BYTES or image_len == 0:
                raise BrnError("Invalid size fields")
            header_raw = fh.read(header_len)
            image_bytes = fh.read(image_len)
            if len(header_raw) != header_len or len(image_bytes) != image_len or fh.read(1):
                raise BrnError("File is truncated or has extra data")
    except OSError as exc:
        raise BrnError(f"Cannot read {path.name}: {exc}") from exc

    try:
        header = json.loads(header_raw.decode("utf-8"))
        if not isinstance(header, dict):
            raise ValueError("header must be an object")
        if hashlib.sha256(image_bytes).hexdigest() != header.get("image_sha256"):
            raise BrnError("Image data is corrupted")
        width, height = header["width"], header["height"]
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (width, height)):
            raise ValueError("invalid image size")
        raw_faces = header["faces"]
        if not isinstance(raw_faces, list):
            raise ValueError("faces must be a list")
        faces = [FaceBox.from_dict(item) for item in raw_faces]
        name = header.get("image_name", "")
        name = Path(name).name[:255] if isinstance(name, str) else ""
        edits = header.get("edits")
    except (ValueError, KeyError) as exc:  # includes JSON and Unicode decode errors
        raise BrnError(f"Invalid Boran header: {exc}") from exc

    return BrnFile(image_bytes, name or path.stem, (width, height), faces, edits if isinstance(edits, dict) else None)
