"""Image decoding: everything Pillow reads, plus HEIC/HEIF/AVIF, JPEG XL and camera RAW when the plugins are installed."""
from __future__ import annotations

import io
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

RAW_EXTENSIONS = frozenset({
    ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".orf", ".rw2", ".raf",
    ".pef", ".srw", ".3fr", ".erf", ".kdc", ".mrw", ".x3f", ".iiq", ".mef", ".mos", ".dcr", ".raw",
})
# Pillow can open these, but they are not photographs a person would name faces in.
_EXCLUDED = frozenset({
    ".eps", ".ps", ".wmf", ".emf", ".mpg", ".mpeg", ".fits", ".fit", ".fts", ".gbr", ".mic", ".msp", ".psd",
    ".bufr", ".grib", ".h5", ".hdf", ".fli", ".flc", ".ftc", ".ftu", ".iim", ".im", ".cur",
})

_plugin_lock = threading.Lock()
_plugins_ready = False


class ImageFormatError(ValueError):
    """The file is not an image this install can decode."""


def register_plugins() -> None:
    """Register the optional decoders once; safe to call from any thread."""
    global _plugins_ready
    with _plugin_lock:
        if _plugins_ready:
            return
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass
        try:
            import pillow_jxl  # noqa: F401  registers JPEG XL with Pillow
        except ImportError:
            pass
        _plugins_ready = True


@lru_cache(maxsize=1)
def supported_extensions() -> frozenset[str]:
    """Lower-case extensions (with dot) that can be opened."""
    register_plugins()
    exts = {ext for ext, fmt in Image.registered_extensions().items() if fmt in Image.OPEN}
    return frozenset((exts | RAW_EXTENSIONS) - _EXCLUDED)


def load(source: Path | bytes, name: str | None = None) -> Image.Image:
    """Decode to an upright RGB image. `name` supplies the extension when `source` is bytes."""
    register_plugins()
    ext = Path(name if name is not None else str(source)).suffix.lower()
    if ext in RAW_EXTENSIONS:
        return _load_raw(source)
    try:
        with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as raw:
            image = ImageOps.exif_transpose(raw)
            return image if image.mode == "RGB" else image.convert("RGB")
    except Image.UnidentifiedImageError as exc:
        raise ImageFormatError(_missing_plugin_hint(ext)) from exc


def _load_raw(source: Path | bytes) -> Image.Image:
    try:
        import rawpy
    except ImportError:
        return _raw_preview(source)
    try:
        with rawpy.imread(io.BytesIO(source) if isinstance(source, bytes) else str(source)) as raw:
            # Half-size demosaic is several times faster and uses a quarter of the memory.
            rgb = raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8)
    except (rawpy.LibRawError, OSError) as exc:
        raise ImageFormatError(f"Cannot decode this RAW file: {exc}") from exc
    return Image.fromarray(rgb)


_JPEG_START = b"\xff\xd8\xff"


def _raw_preview(source: Path | bytes) -> Image.Image:
    """Largest JPEG embedded in a TIFF-style RAW file (DNG, CR2, NEF, ARW, ...); no extra package needed."""
    data = source if isinstance(source, bytes) else source.read_bytes()
    best: tuple[int, int] | None = None  # (area, offset)
    pos = data.find(_JPEG_START)
    while pos != -1:
        try:
            with Image.open(io.BytesIO(data[pos:])) as candidate:
                if candidate.format == "JPEG" and (best is None or candidate.width * candidate.height > best[0]):
                    best = (candidate.width * candidate.height, pos)
        except (OSError, ValueError):
            pass  # not a decodable JPEG (e.g. the lossless-JPEG sensor data in DNG)
        pos = data.find(_JPEG_START, pos + 3)
    if best is None:
        raise ImageFormatError("No preview image found in this RAW file. For full RAW decoding: pip install rawpy")
    with Image.open(io.BytesIO(data[best[1]:])) as preview:
        image = ImageOps.exif_transpose(preview)
        return image if image.mode == "RGB" else image.convert("RGB")


def _missing_plugin_hint(ext: str) -> str:
    if ext in {".heic", ".heif", ".hif", ".avif", ".heics", ".heifs", ".avci", ".avcs"}:
        return "HEIC/HEIF/AVIF files need the plugin: pip install pillow-heif"
    if ext == ".jxl":
        return "JPEG XL files need the plugin: pip install pillow-jxl-plugin"
    return "This file is not a recognised image format"
