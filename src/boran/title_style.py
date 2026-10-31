from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

POSITIONS = {
    "Top center": "top", "Top left": "top-left", "Top right": "top-right",
    "Bottom center": "bottom", "Bottom left": "bottom-left", "Bottom right": "bottom-right",
}
SHAPES = {"Pill": "pill", "Rounded box": "round", "Banner": "bar", "Plain text": "plain"}
MOTIONS = {
    "Slide down": "slide", "Rise up": "rise", "Slide sideways": "side", "Fade": "fade", "Zoom": "zoom",
    "Typewriter": "type", "Letters rise": "letters_rise", "Letters drop": "letters_drop",
    "Letters fade": "letters_fade", "Decode": "scramble", "None": "none",
}
LETTER_MOTIONS = frozenset({"letters_rise", "letters_drop", "letters_fade", "scramble"})
EFFECTS = {
    "Shimmer": "shimmer", "Aurora": "aurora", "Gradient flow": "gradient", "Wave": "wave", "Glow": "glow",
    "Pulse": "pulse", "None": "none",
}
LABELS = {"One title at the top": "title", "A label on each face": "individual"}
SHADOWS = {"None": "none", "Soft": "soft", "Strong": "strong", "Glow": "glow"}
BOX_MOTIONS = {"Grow": "grow", "Fade": "fade", "Slide": "slide", "None": "none"}
EASING_LABELS = {
    "Linear": "linear", "Ease in": "ease-in", "Ease out": "ease-out", "Ease in-out": "ease-in-out", "Sine": "sine",
    "Expo out": "expo-out", "Back (overshoot)": "back-out", "Bounce": "bounce-out", "Elastic": "elastic-out",
}
MIN_SIZE, MAX_SIZE = 12, 96
MIN_SPEED, MAX_SPEED = 25, 300
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass(frozen=True)
class TitleStyle:
    """How the hovered person's name is shown in Full View. An empty `font` means the app font.

    `x` and `y` are where the user dragged the title (its centre as a fraction of the screen); both None means
    the `position` preset.
    """

    position: str = "top"
    font: str = ""
    size: int = 26
    shape: str = "pill"
    motion: str = "slide"  # how the text arrives
    effect: str = "shimmer"  # keeps animating while the name is shown
    labels: str = "title"  # Full View: one title for whoever is hovered, or a box and label on each face
    text_color: str = "#ffffff"
    accent: str = "#5b9bff"  # glow, pulse and the far end of the gradient
    accent_opacity: int = 100  # 0 is a transparent accent: those effects vanish
    bg_color: str = "#17171c"
    bg_opacity: int = 100  # 0 is a transparent background
    border: bool = True  # the thin lighter outline around the box
    shadow: str = "soft"
    box_motion: str = "grow"  # how the box arrives
    easing: str = "ease-out"
    speed: int = 100  # percent; scales the looping effects
    x: float | None = None
    y: float | None = None

    def anchor(self) -> tuple[str, str]:
        """(vertical, horizontal) = ("top" | "bottom", "left" | "center" | "right")."""
        vertical = "top" if self.position.startswith("top") else "bottom"
        horizontal = "left" if self.position.endswith("left") else "right" if self.position.endswith("right") else "center"
        return vertical, horizontal


def _number(value: object, low: int, high: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(high, max(low, value))


def sanitize(raw: object) -> TitleStyle:
    """Build a valid style from untrusted data; anything missing or invalid falls back to the default."""
    default = TitleStyle()
    if not isinstance(raw, dict):
        return default
    values: dict = {}
    choices = (
        ("position", POSITIONS), ("shape", SHAPES), ("motion", MOTIONS), ("effect", EFFECTS), ("labels", LABELS),
        ("shadow", SHADOWS), ("box_motion", BOX_MOTIONS), ("easing", EASING_LABELS),
    )
    for name, allowed in choices:
        value = raw.get(name)
        values[name] = value if value in allowed.values() else getattr(default, name)
    for name in ("text_color", "accent", "bg_color"):
        value = raw.get(name)
        values[name] = value.lower() if isinstance(value, str) and _HEX.fullmatch(value) else getattr(default, name)
    font = raw.get("font")
    values["font"] = font.strip()[:80] if isinstance(font, str) else default.font
    values["size"] = _number(raw.get("size"), MIN_SIZE, MAX_SIZE, default.size)
    values["bg_opacity"] = _number(raw.get("bg_opacity"), 0, 100, default.bg_opacity)
    values["accent_opacity"] = _number(raw.get("accent_opacity"), 0, 100, default.accent_opacity)
    values["border"] = raw["border"] if isinstance(raw.get("border"), bool) else default.border
    values["speed"] = _number(raw.get("speed"), MIN_SPEED, MAX_SPEED, default.speed)
    x, y = raw.get("x"), raw.get("y")
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in (x, y)):
        values["x"], values["y"] = float(x), float(y)
    return TitleStyle(**values)


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / ".config") / "Boran" / "settings.json"


def load_title_style(path: Path | None = None) -> TitleStyle:
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return TitleStyle()
    return sanitize(data.get("title") if isinstance(data, dict) else None)


def save_title_style(style: TitleStyle, path: Path | None = None) -> bool:
    """Store the style, keeping any other settings in the file. Returns False if it couldn't be written."""
    target = path or settings_path()
    try:
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["title"] = asdict(style)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, target)
        return True
    except OSError:
        return False
