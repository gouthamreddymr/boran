"""Non-destructive photo edits: adjustments and looks, stored beside the untouched original in the .brn file."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
from PIL import Image, ImageFilter

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass(frozen=True)
class Adjustment:
    key: str
    label: str
    group: str
    low: int = -100
    high: int = 100


ADJUSTMENTS: tuple[Adjustment, ...] = (
    Adjustment("exposure", "Exposure", "Light"),
    Adjustment("contrast", "Contrast", "Light"),
    Adjustment("highlights", "Highlights", "Light"),
    Adjustment("shadows", "Shadows", "Light"),
    Adjustment("saturation", "Saturation", "Color"),
    Adjustment("vibrance", "Vibrance", "Color"),
    Adjustment("warmth", "Warmth", "Color"),
    Adjustment("tint", "Tint", "Color"),
    Adjustment("sharpness", "Sharpness", "Detail", 0, 100),
    Adjustment("fade", "Fade", "Effects", 0, 100),
    Adjustment("vignette", "Vignette", "Effects"),
    Adjustment("grain", "Grain", "Effects", 0, 100),
)
_LIMITS = {a.key: (a.low, a.high) for a in ADJUSTMENTS}


@dataclass(frozen=True)
class Look:
    """A preset: adjustment values plus an optional black-and-white mix and a shadow/highlight colour wash."""

    label: str
    adjust: Mapping[str, float] = field(default_factory=dict)
    mono: float = 0.0
    tone: tuple[str, str, float] | None = None  # shadow colour, highlight colour, strength 0..1


LOOKS: dict[str, Look] = {
    "original": Look("Original"),
    "vivid": Look("Vivid", {"saturation": 32, "vibrance": 15, "contrast": 12}),
    "vivid_warm": Look("Vivid Warm", {"saturation": 30, "vibrance": 15, "contrast": 12, "warmth": 22}),
    "vivid_cool": Look("Vivid Cool", {"saturation": 30, "vibrance": 15, "contrast": 12, "warmth": -22}),
    "dramatic": Look("Dramatic", {"contrast": 42, "saturation": -14, "shadows": -22, "highlights": -16, "vignette": 25}),
    "dramatic_warm": Look(
        "Dramatic Warm", {"contrast": 42, "saturation": -10, "shadows": -22, "highlights": -16, "vignette": 25, "warmth": 20}
    ),
    "dramatic_cool": Look(
        "Dramatic Cool", {"contrast": 42, "saturation": -10, "shadows": -22, "highlights": -16, "vignette": 25, "warmth": -20}
    ),
    "mono": Look("Mono", {"contrast": 8}, mono=1.0),
    "silvertone": Look("Silvertone", {"contrast": 14, "fade": 10}, mono=1.0, tone=("#1c2733", "#eef3fa", 0.28)),
    "noir": Look("Noir", {"contrast": 58, "shadows": -26, "vignette": 38}, mono=1.0),
    "fade": Look("Fade", {"fade": 38, "saturation": -20, "contrast": -10}),
    "chrome": Look(
        "Chrome", {"saturation": 22, "contrast": 22, "highlights": -10}, tone=("#0d2a3a", "#ffe9c9", 0.14)
    ),
    "instant": Look(
        "Instant", {"warmth": 18, "fade": 24, "saturation": -8, "vignette": 16}, tone=("#2b1a3d", "#ffe2b8", 0.16)
    ),
    "cinematic": Look("Cinematic", {"contrast": 20, "saturation": -8}, tone=("#0b4a58", "#ffb066", 0.3)),
    "matte": Look("Matte", {"fade": 42, "contrast": -8, "shadows": 20}),
    "golden_hour": Look("Golden Hour", {"warmth": 40, "exposure": 8, "tint": 6, "highlights": -10, "vibrance": 10}),
}


def _clamp_int(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return max(low, min(high, round(value)))


@dataclass(frozen=True)
class Edits:
    """What the user did to a photo. `adjust` holds only non-zero slider values."""

    look: str = "original"
    amount: int = 100  # how strongly the look applies, 0..100
    adjust: Mapping[str, int] = field(default_factory=dict)

    def is_identity(self) -> bool:
        return (self.look == "original" or self.amount == 0) and not any(self.adjust.values())

    def value(self, key: str) -> int:
        return self.adjust.get(key, 0)

    def with_adjust(self, key: str, value: int) -> Edits:
        low, high = _LIMITS[key]
        adjust = {k: v for k, v in self.adjust.items() if k != key}
        if (clamped := max(low, min(high, int(value)))) != 0:
            adjust[key] = clamped
        return Edits(self.look, self.amount, adjust)

    def with_look(self, look: str, amount: int | None = None) -> Edits:
        return Edits(look if look in LOOKS else "original", self.amount if amount is None else max(0, min(100, amount)), self.adjust)

    def to_dict(self) -> dict:
        return {"look": self.look, "amount": self.amount, "adjust": dict(sorted(self.adjust.items()))}

    @classmethod
    def from_dict(cls, raw: object) -> Edits:
        """Build edits from untrusted data (a file header); anything invalid is ignored."""
        if not isinstance(raw, dict):
            return cls()
        look = raw.get("look")
        amount = _clamp_int(raw.get("amount"), 0, 100)
        adjust: dict[str, int] = {}
        if isinstance(raw.get("adjust"), dict):
            for key, value in raw["adjust"].items():
                if key in _LIMITS and (v := _clamp_int(value, *_LIMITS[key])):
                    adjust[key] = v
        return cls(look if look in LOOKS else "original", 100 if amount is None else amount, adjust)


def _effective(edits: Edits) -> tuple[dict[str, float], float, tuple[str, str, float] | None]:
    """Slider values after adding the look (scaled by its strength), the mono mix and the colour wash."""
    look = LOOKS.get(edits.look, LOOKS["original"])
    k = edits.amount / 100.0
    values = {key: look.adjust.get(key, 0) * k + edits.value(key) for key in _LIMITS}
    for key, (low, high) in _LIMITS.items():
        values[key] = max(low, min(high, values[key]))
    tone = (look.tone[0], look.tone[1], look.tone[2] * k) if look.tone else None
    return values, look.mono * k, tone


def _rgb(color: str) -> np.ndarray:
    return np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32) / 255.0


def apply(
    image: Image.Image, edits: Edits, region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0), scale: float = 1.0
) -> Image.Image:
    """Return `image` with the edits applied.

    `region` is where this image sits in the whole photo (fractions x0, y0, x1, y1), so the vignette stays centred
    on the photo; `scale` is the on-screen zoom, so sharpening keeps the same look at any zoom.
    """
    if edits.is_identity():
        return image
    p, mono, tone = _effective(edits)
    a = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
    h, w = a.shape[:2]

    if p["exposure"]:
        a *= 2.0 ** (p["exposure"] / 50.0)
    if p["warmth"]:
        a[..., 0] *= 1 + 0.25 * p["warmth"] / 100
        a[..., 2] *= 1 - 0.25 * p["warmth"] / 100
    if p["tint"]:
        a[..., 1] *= 1 - 0.18 * p["tint"] / 100
    np.clip(a, 0.0, 1.0, out=a)

    if p["shadows"] or p["highlights"]:
        lum = a @ _LUMA
        if p["shadows"]:
            a += ((p["shadows"] / 100) * 0.35 * (1 - lum) ** 2)[..., None]
        if p["highlights"]:
            a += ((p["highlights"] / 100) * 0.35 * lum**2)[..., None]
    if p["contrast"]:
        a = (a - 0.5) * (1 + 0.9 * p["contrast"] / 100) + 0.5
    if p["fade"]:
        lift = 0.15 * p["fade"] / 100
        a = lift + a * (1 - lift)
    np.clip(a, 0.0, 1.0, out=a)

    if p["saturation"] or p["vibrance"]:
        gray = (a @ _LUMA)[..., None]
        if p["saturation"]:
            a = gray + (a - gray) * (1 + p["saturation"] / 100)
        if p["vibrance"]:
            chroma = a.max(axis=2, keepdims=True) - a.min(axis=2, keepdims=True)  # muted colours gain the most
            a = gray + (a - gray) * (1 + (p["vibrance"] / 100) * (1 - np.clip(chroma, 0, 1)))
        np.clip(a, 0.0, 1.0, out=a)
    if mono:
        gray = (a @ _LUMA)[..., None]
        a = a * (1 - mono) + gray * mono
    if tone:
        lum = a @ _LUMA
        shadow, highlight = _rgb(tone[0]) - 0.5, _rgb(tone[1]) - 0.5
        a = a + tone[2] * (((1 - lum) ** 2)[..., None] * shadow + (lum**2)[..., None] * highlight)

    if p["vignette"]:
        x0, y0, x1, y1 = region
        fx = (x0 + (np.arange(w, dtype=np.float32) + 0.5) / w * (x1 - x0) - 0.5) * 2
        fy = (y0 + (np.arange(h, dtype=np.float32) + 0.5) / h * (y1 - y0) - 0.5) * 2
        r2 = np.clip((fy[:, None] ** 2 + fx[None, :] ** 2) / 2, 0.0, 1.0)
        a = a * (1 - 0.8 * p["vignette"] / 100 * r2)[..., None]
    if p["grain"]:
        noise = np.random.default_rng(7).standard_normal((h, w)).astype(np.float32)
        a = a + (noise * 0.07 * p["grain"] / 100)[..., None]

    np.clip(a, 0.0, 1.0, out=a)
    out = Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), "RGB")
    if p["sharpness"]:
        radius = max(0.5, min(6.0, 1.2 * scale))
        out = out.filter(ImageFilter.UnsharpMask(radius=radius, percent=int(180 * p["sharpness"] / 100), threshold=2))
    return out
