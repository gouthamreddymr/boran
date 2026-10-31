from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from boran.models import FaceBox

if TYPE_CHECKING:
    from PIL import Image

MAX_SIDE = 8000  # larger images are downscaled to bound memory
_YUNET_MODEL = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"

_SCORE = 0.6
_GLOBAL_SIDE = 1280
_TILE_OUT = 800  # tile size fed to the detector, in pixels
_WORK_PIXELS = 40_000_000  # budget for the tile pass; decides the upscale (1x-3x)
_EDGE_PX = 3
_MIN_FACE_PX = 8
_NMS_IOU = 0.4
_CONTAINED = 0.8

_Box = tuple[float, float, float, float]
_Cand = tuple[float, float, float, float, float]  # x, y, w, h, score
Progress = Callable[[float, str], None]  # fraction 0..1, status text


def detect_faces(image: "Image.Image", progress: Progress | None = None) -> list[FaceBox]:
    """Detect faces; boxes are in the image's pixel coordinates.

    Runs YuNet over the whole image plus overlapping upscaled tiles, so small
    faces in large group photos are found, then merges duplicates.
    Falls back to a Haar cascade if the YuNet model is missing.
    OpenCV is imported here so the app starts without paying for it.
    `progress` is called from the calling thread as work advances.
    """
    import cv2
    import numpy as np
    from PIL import Image

    def report(fraction: float, text: str) -> None:
        if progress is not None:
            progress(fraction, text)

    w, h = image.size
    if w < 1 or h < 1:
        return []
    report(0.0, "Decoding pixels and normalising colour space")
    scale = min(1.0, MAX_SIDE / max(w, h))
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    if scale < 1.0:
        rgb = rgb.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.BILINEAR)
    bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)

    detector = _load_yunet(cv2)
    if detector is not None:
        cands = _scan(cv2, detector, bgr, report)
    else:
        report(0.5, "Running Haar cascade classifier (fallback detector)")
        cands = _haar(cv2, bgr)

    report(0.97, "Merging candidates with non-maximum suppression")
    faces: list[FaceBox] = []
    for bx, by, bw, bh in _merge(cands):
        x0, y0 = max(0, round(bx / scale)), max(0, round(by / scale))
        x1, y1 = min(w, round((bx + bw) / scale)), min(h, round((by + bh) / scale))
        if x1 - x0 >= _MIN_FACE_PX and y1 - y0 >= _MIN_FACE_PX:
            faces.append(FaceBox(x0, y0, x1 - x0, y1 - y0))
    faces.sort(key=lambda f: (f.y // max(1, f.h), f.x))
    return faces


def _load_yunet(cv2):
    if not _YUNET_MODEL.is_file():
        return None
    try:
        return cv2.FaceDetectorYN.create(str(_YUNET_MODEL), "", (320, 320), score_threshold=_SCORE)
    except (cv2.error, AttributeError):
        return None


def _starts(total: int, size: int, overlap: int) -> list[int]:
    if total <= size:
        return [0]
    starts = list(range(0, total - size, size - overlap))
    starts.append(total - size)
    return starts


def _scan(cv2, detector, bgr, report: Progress) -> list[_Cand]:
    H, W = bgr.shape[:2]
    up = max(1, min(3, int((_WORK_PIXELS / (W * H)) ** 0.5)))
    size = _TILE_OUT // up
    ys, xs = _starts(H, size, size * 3 // 10), _starts(W, size, size * 3 // 10)
    total = 1 + len(ys) * len(xs)
    done = 0
    out: list[_Cand] = []

    def run(img, ox: int, oy: int, scale: float, interior: tuple[bool, bool, bool, bool]) -> None:
        nonlocal done
        ih, iw = img.shape[:2]
        detector.setInputSize((iw, ih))
        _, res = detector.detect(img)
        done += 1
        scaling = f", {up}x bicubic upscale" if up > 1 else ""
        report(0.02 + 0.93 * done / total, f"Multi-scale CNN inference: tile {done - 1}/{total - 1}{scaling}")
        if res is None:
            return
        left, top, right, bottom = interior
        for r in res:
            x, y, bw, bh, score = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[14])
            # Faces cut by an interior tile edge are seen whole in a neighbouring tile.
            if (left and x <= _EDGE_PX) or (top and y <= _EDGE_PX):
                continue
            if (right and x + bw >= iw - _EDGE_PX) or (bottom and y + bh >= ih - _EDGE_PX):
                continue
            out.append((ox + x / scale, oy + y / scale, bw / scale, bh / scale, score))

    # Pass 1: whole image, for large faces.
    report(0.02, "Multi-scale CNN inference: full-frame pass")
    g = min(1.0, _GLOBAL_SIDE / max(H, W))
    whole = bgr if g == 1.0 else cv2.resize(bgr, (round(W * g), round(H * g)), interpolation=cv2.INTER_AREA)
    run(whole, 0, 0, g, (False, False, False, False))

    # Pass 2: tiles, upscaled when the image is small enough, for small and medium faces.
    _tiles(run, bgr, size, ys, xs, up, cv2)
    return out


def _tiles(run, bgr, size: int, ys: list[int], xs: list[int], up: int, cv2) -> None:
    H, W = bgr.shape[:2]
    for y in ys:
        for x in xs:
            tile = bgr[y : y + size, x : x + size]
            if up > 1:
                tile = cv2.resize(tile, (tile.shape[1] * up, tile.shape[0] * up), interpolation=cv2.INTER_CUBIC)
            interior = (x > 0, y > 0, x + size < W, y + size < H)
            run(tile, x, y, float(up), interior)


def _haar(cv2, bgr) -> list[_Cand]:
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if cascade.empty():
        return []
    gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return [(float(x), float(y), float(w), float(h), 1.0) for x, y, w, h in found]


def _overlap(a: _Box, b: _Box) -> tuple[float, float]:
    """Return (IoU, intersection / smaller area)."""
    iw = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    ih = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0, 0.0
    inter = iw * ih
    area_a, area_b = a[2] * a[3], b[2] * b[3]
    return inter / (area_a + area_b - inter), inter / min(area_a, area_b)


def _merge(cands: list[_Cand]) -> list[_Box]:
    """Non-maximum suppression that also drops boxes mostly inside a better one."""
    kept: list[_Box] = []
    for x, y, w, h, _score in sorted(cands, key=lambda c: -c[4]):
        if w <= 0 or h <= 0:
            continue
        box = (x, y, w, h)
        if all(_distinct(box, k) for k in kept):
            kept.append(box)
    return kept


def _distinct(a: _Box, b: _Box) -> bool:
    iou, contained = _overlap(a, b)
    return iou < _NMS_IOU and contained < _CONTAINED
