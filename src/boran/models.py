from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class FaceBox:
    """Face rectangle in image pixel coordinates."""

    x: int
    y: int
    w: int
    h: int
    name: str = ""

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "name": self.name}

    @classmethod
    def from_dict(cls, data: Any) -> "FaceBox":
        if not isinstance(data, dict):
            raise ValueError("face entry must be an object")
        try:
            values = [float(data[k]) for k in ("x", "y", "w", "h")]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid face geometry: {exc}") from exc
        if not all(math.isfinite(v) for v in values):
            raise ValueError("face geometry must be finite")
        x, y, w, h = (int(round(v)) for v in values)
        if w <= 0 or h <= 0:
            raise ValueError("face width/height must be positive")
        name = data.get("name", "")
        if not isinstance(name, str):
            raise ValueError("face name must be a string")
        return cls(x, y, w, h, name.strip())


def iou(a: FaceBox, b: FaceBox) -> float:
    iw = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    ih = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / (a.w * a.h + b.w * b.h - inter)


def face_at(faces: Iterable[FaceBox], px: float, py: float) -> int | None:
    """Index of the smallest face containing the point, or None."""
    best: int | None = None
    best_area = 0
    for i, face in enumerate(faces):
        if face.contains(px, py):
            area = face.w * face.h
            if best is None or area < best_area:
                best, best_area = i, area
    return best
