from __future__ import annotations

import math
import random
import tkinter as tk
from tkinter import font as tkfont
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from boran.easing import ease
from boran.title_style import LETTER_MOTIONS, TitleStyle
from boran.ui import fonts

_PAD = {"pill": (30, 12), "round": (26, 12), "bar": (28, 14), "plain": (0, 0)}  # horizontal, vertical text padding
_MARGIN = 24  # gap to the screen edge
_GROW_FROM = 0.6  # a box that appears or disappears grows from / shrinks to this fraction of its width
_STAGGER = 0.8  # how far apart the letters of a per-letter transition start
_TRAVEL_PX = {"slide": 12, "rise": 14, "side": 44, "letters_rise": 16, "letters_drop": 16}
_SHADOWS = {"soft": (14, 6, 0.55), "strong": (8, 8, 0.85), "glow": (18, 0, 0.8)}  # blur, offset down, opacity
_SHADOW_MARGIN = 40  # room around the box for its shadow
_BORDER_MIX = 0.14  # how far the box outline is lightened from the background colour
EXIT_SECONDS = 0.25
EFFECT_SECONDS = {"shimmer": 2.6, "aurora": 6.0, "gradient": 4.0, "wave": 1.8, "glow": 2.0, "pulse": 2.2}  # one cycle
_LETTER_EFFECTS = frozenset({"shimmer", "aurora", "gradient", "wave", "glow"})
_AURORA = ("#5b9bff", "#a47bff", "#ff7ac0", "#ffb86b", "#5b9bff")
_SCRAMBLE = "abcdeghknopqrsuvxyzABCDEFGHKLNOPRSTUVXYZ0123456789+=?*#"  # no wide glyphs, so letters don't overlap
_FONTS: dict[tuple, tkfont.Font] = {}
_PLATES: dict[tuple, Image.Image] = {}


class Layout(NamedTuple):
    x: float
    y: float
    width: float
    height: float
    text_x: float  # centre of the text
    text_y: float


def rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def blend(a: str, b: str, t: float) -> str:
    """Colour `t` of the way from `a` to `b` (both "#rrggbb")."""
    t = min(1.0, max(0.0, t))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(rgb(a), rgb(b)))


def round_rect_points(x0: float, y0: float, x1: float, y1: float, r: float) -> list[float]:
    """Control points for a smooth=True polygon that draws a rounded rectangle."""
    return [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
        x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]


def duration(style: TitleStyle, text: str) -> float:
    """Seconds a name takes to come in."""
    if style.motion == "none" and style.box_motion == "none":
        return 0.0
    letters = len(text)
    base = {
        "type": min(1.2, max(0.35, 0.2 + 0.045 * letters)),
        "scramble": min(1.4, 0.6 + 0.05 * letters),
        "letters_rise": min(1.4, 0.5 + 0.045 * letters),
        "letters_drop": min(1.4, 0.5 + 0.045 * letters),
        "letters_fade": min(1.4, 0.5 + 0.045 * letters),
    }.get(style.motion, 0.4)
    return base * (1.5 if style.easing in ("bounce-out", "elastic-out") else 1.0)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def layout(cw: float, ch: float, text_w: float, text_h: float, style: TitleStyle, scale: float = 1.0) -> Layout:
    """Where the title's box (or bare text) goes on a `cw` x `ch` screen."""
    pad_x, pad_y = (v * scale for v in _PAD[style.shape])
    margin = _MARGIN * scale
    vertical, horizontal = style.anchor()
    w, h = text_w + 2 * pad_x, text_h + 2 * pad_y
    free_x = style.x * cw if style.x is not None and style.y is not None else None
    free_y = style.y * ch if free_x is not None else None
    if style.shape == "bar":  # full width
        x, w = 0.0, cw
        y = _clamp(free_y - h / 2, 0, max(0.0, ch - h)) if free_y is not None else (0.0 if vertical == "top" else ch - h)
        text_x = {"left": margin + pad_x + text_w / 2, "right": cw - margin - pad_x - text_w / 2}.get(horizontal, cw / 2)
    else:
        if free_x is not None and free_y is not None:
            x = _clamp(free_x - w / 2, 0, max(0.0, cw - w))
            y = _clamp(free_y - h / 2, 0, max(0.0, ch - h))
        else:
            x = {"left": margin, "right": cw - margin - w}.get(horizontal, (cw - w) / 2)
            y = margin if vertical == "top" else ch - margin - h
        text_x = x + w / 2
    return Layout(x, y, w, h, text_x, y + h / 2)


def _font(canvas: tk.Canvas, spec: tuple) -> tkfont.Font:
    key = (str(canvas.winfo_toplevel()), *spec)
    cached = _FONTS.get(key)
    try:
        if cached is not None:
            cached.metrics()
            return cached
    except tk.TclError:  # the Tk root it belonged to is gone
        pass
    face = _FONTS[key] = tkfont.Font(root=canvas, family=spec[0], size=spec[1], weight=spec[2])
    return face


def _measure(canvas: tk.Canvas, text: str, font: tuple, wrap: float) -> tuple[float, float]:
    if not text:
        return 0.0, 0.0
    probe = canvas.create_text(0, 0, text=text, font=font, anchor="nw", width=wrap)
    x0, y0, x1, y1 = canvas.bbox(probe)
    canvas.delete(probe)
    return x1 - x0, y1 - y0


def _plate_image(w: int, h: int, radius: float, style: TitleStyle, margin: int) -> Image.Image:
    """The box with its soft shadow as RGBA, drawn at 2x and shrunk for smooth edges. Cached by size."""
    key = (w, h, round(radius), style.bg_color, style.bg_opacity, style.border, style.shadow, style.accent, style.accent_opacity, margin)
    cached = _PLATES.get(key)
    if cached is not None:
        return cached
    scale = 2
    size = ((w + 2 * margin) * scale, (h + 2 * margin) * scale)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    opacity = style.bg_opacity / 100
    accent = style.accent_opacity / 100
    if style.shadow in _SHADOWS and opacity > 0.05 and (style.shadow != "glow" or accent > 0):
        blur, drop, strength = _SHADOWS[style.shadow]
        if style.shadow == "glow":
            strength *= accent
        mask = Image.new("L", size, 0)
        top = (margin + drop * margin / _SHADOW_MARGIN) * scale
        ImageDraw.Draw(mask).rounded_rectangle(
            (margin * scale, top, (margin + w) * scale - 1, top + h * scale - 1), radius * scale, fill=255
        )
        mask = mask.filter(ImageFilter.GaussianBlur(blur * margin / _SHADOW_MARGIN * scale / 2))
        shadow = Image.new("RGBA", size, rgb(style.accent if style.shadow == "glow" else "#000000") + (0,))
        shadow.putalpha(mask.point(lambda v: int(v * strength * opacity)))
        image = Image.alpha_composite(image, shadow)
    if opacity > 0:
        draw = ImageDraw.Draw(image)
        box = (margin * scale, margin * scale, (margin + w) * scale - 1, (margin + h) * scale - 1)
        outline = rgb(_lighten(style.bg_color)) + (round(255 * opacity),) if style.border else None
        draw.rounded_rectangle(
            box, radius * scale, fill=rgb(style.bg_color) + (round(255 * opacity),), outline=outline, width=scale
        )
    image = image.resize((w + 2 * margin, h + 2 * margin), Image.Resampling.LANCZOS)
    if len(_PLATES) > 24:
        _PLATES.clear()
    _PLATES[key] = image
    return image


def _lighten(color: str) -> str:
    return blend(color, "#ffffff", _BORDER_MIX)


def _palette(stops: tuple[str, ...], t: float) -> str:
    position = (t % 1.0) * (len(stops) - 1)
    i = int(position)
    return blend(stops[i], stops[min(i + 1, len(stops) - 1)], position - i)


def _letter_colors(effect: str, count: int, cycle: float, style: TitleStyle) -> list[str]:
    """Colour of each letter for a looping effect; `cycle` counts whole turns of the animation."""
    base = style.text_color
    accent = style.accent_opacity / 100
    colors = []
    for i in range(count):
        u = (i + 0.5) / count
        if effect == "aurora":
            colors.append(blend(_palette(_AURORA, u * 0.7 + cycle), "#ffffff", 0.25))
        elif effect == "gradient":
            mix = 0.5 + 0.5 * math.sin(2 * math.pi * (u * 0.9 + ease(style.easing, cycle % 1.0)))
            colors.append(blend(base, style.accent, mix * accent))
        elif effect == "shimmer":  # a bright band with a glow sweeps past, resting off-screen between passes
            band = math.exp(-(((u - (ease(style.easing, cycle % 1.0) * 1.7 - 0.35)) / 0.14) ** 2))
            dim = blend(base, "#000000", 0.2)
            colors.append(blend(blend(dim, blend(style.accent, "#ffffff", 0.4), 0.6 * band * accent), "#ffffff", band**3))
        else:
            colors.append(base)
    return colors


def draw_title(
    canvas: tk.Canvas, text: str, style: TitleStyle, progress: float = 1.0, scale: float = 1.0,
    tag: str = "title", previous: str = "", clock: float = 0.0,
) -> None:
    """Draw (replacing any earlier drawing with `tag`) the title, or its transition.

    `progress` runs 0..1 in a straight line; the style's easing curve is applied here. With `previous` set the old
    name leaves while `text` arrives; an empty `text` with a `previous` is the exit, and an empty `previous` is the
    entrance. Draws nothing when both are empty. Once settled, the style's effect animates with `clock` (seconds).
    """
    canvas.delete(tag)
    photos: dict = canvas.__dict__.setdefault("_title_photos", {})
    photos.pop(tag, None)
    motion = style.motion
    if motion == "none" and style.box_motion == "none":
        previous, progress = "", 1.0
    if not text and not previous:
        return
    cw, ch = canvas.winfo_width(), canvas.winfo_height()
    base_size = max(6, round(style.size * scale))
    font = (style.font or fonts.family(), base_size, "bold")
    face = _font(canvas, font)
    pad_x = _PAD[style.shape][0] * scale
    wrap = max(60 * scale, cw - 2 * (_MARGIN * scale + pad_x))
    new_w, new_h = _measure(canvas, text, font, wrap)
    old_w, old_h = _measure(canvas, previous, font, wrap)

    p = _clamp(progress)
    entering, exiting = bool(text) and not previous, not text
    eased = ease(style.easing, p)
    presence = eased if entering else 1 - eased if exiting else 1.0  # how much of the box is on screen
    if style.box_motion == "grow":
        if entering or exiting:
            width = (new_w or old_w) * (_GROW_FROM + (1 - _GROW_FROM) * _clamp(presence, 0.0, 1.2))
        else:
            width = old_w + (new_w - old_w) * _clamp(eased)
    else:
        width = new_w or old_w
    lay = layout(cw, ch, width, max(new_h, old_h), style, scale)
    vertical = style.anchor()[0]
    box_dy = 0.0
    if style.box_motion == "slide" and not (text and previous):
        box_dy = (1 - presence) * (lay.height + _MARGIN * scale) * (-1 if vertical == "top" else 1)
    text_y = lay.text_y + box_dy

    settled = bool(text) and not previous and p >= 1.0
    effect = style.effect if settled else "none"
    cycle = clock * style.speed / 100 / EFFECT_SECONDS.get(effect, 1.0) if effect != "none" else 0.0
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * cycle) if effect in ("pulse", "glow") else 0.0

    has_box = style.shape != "plain" and style.bg_opacity > 0
    if has_box:
        margin = max(6, round(_SHADOW_MARGIN * scale))
        radius = {"pill": lay.height / 2, "round": min(16 * scale, lay.height / 2), "bar": 0.0}[style.shape]
        image = _plate_image(max(1, round(lay.width)), max(1, round(lay.height)), radius, style, margin)
        if style.box_motion == "fade" and presence < 1.0:
            image = image.copy()
            image.putalpha(image.getchannel("A").point(lambda v: int(v * _clamp(presence))))
        photo = ImageTk.PhotoImage(image)
        photos[tag] = photo
        canvas.create_image(lay.x - margin, lay.y + box_dy - margin, anchor="nw", image=photo, tags=tag)
    if effect == "pulse" and style.shape != "plain":
        ring = blend(_lighten(style.bg_color), style.accent, pulse * style.accent_opacity / 100)
        if style.shape == "bar":
            edge = lay.y + box_dy + (lay.height if vertical == "top" else 0)
            canvas.create_line(lay.x, edge, lay.x + lay.width, edge, fill=ring, width=2, tags=tag)
        else:
            r = lay.height / 2 if style.shape == "pill" else min(16 * scale, lay.height / 2)
            canvas.create_polygon(
                round_rect_points(lay.x, lay.y + box_dy, lay.x + lay.width, lay.y + box_dy + lay.height, r),
                smooth=True, fill="", outline=ring, width=2, tags=tag,
            )

    boxless = not has_box
    plate = style.bg_color
    horizontal = style.anchor()[1]
    dx_unit, dy_unit = {"slide": (0, 1 if vertical == "top" else -1), "rise": (0, -1), "side": (-1, 0)}.get(motion, (0, 0))
    travel = _TRAVEL_PX.get(motion, 0) * scale
    shadow_off = max(1, round((3 if style.shadow == "strong" else 2) * scale))
    glow_px = max(1, round(2 * scale))
    accent_level = style.accent_opacity / 100

    def emit(x: float, y: float, content: str, size: int, color: str, visible: float, anchor: str, extra_glow: float = 0.0, **kw) -> None:
        """One piece of text, with the text-level shadow or glow when there is no box behind it."""
        spec = (font[0], size, "bold")
        if accent_level > 0 and (extra_glow > 0 or (boxless and style.shadow == "glow")):
            strength = (extra_glow if extra_glow > 0 else 0.7) * accent_level
            glow = blend(plate, style.accent, strength * visible)
            for ox, oy in ((-glow_px, 0), (glow_px, 0), (0, -glow_px), (0, glow_px)):
                canvas.create_text(x + ox, y + oy, text=content, font=spec, fill=glow, anchor=anchor, tags=tag, **kw)
        elif boxless and style.shadow in ("soft", "strong"):
            canvas.create_text(
                x + shadow_off, y + shadow_off, text=content, font=spec, fill=blend(plate, "#000000", visible), anchor=anchor,
                tags=tag, **kw,
            )
        canvas.create_text(x, y, text=content, font=spec, fill=blend(plate, color, visible), anchor=anchor, tags=tag, **kw)

    def put(content: str, visible: float, shift: float, zoom: float = 1.0, reveal: float = 1.0, color: str | None = None) -> None:
        """Whole-line text. `visible` fades it in; `shift` -1..1 moves it along the motion's travel direction."""
        if not content or visible <= 0:
            return
        x, y = lay.text_x + dx_unit * travel * shift, text_y + dy_unit * travel * shift
        size = max(6, round(base_size * zoom))
        kw = {"width": wrap}
        shown, anchor = content, "center"
        if motion == "type":
            shown = content[: round(len(content) * _clamp(reveal))]
            if not shown:
                return
            anchor = "w"
            x = lay.text_x - _measure(canvas, content, font, wrap)[0] / 2
            kw["justify"] = "left"
        else:
            kw["justify"] = horizontal
        emit(x, y, shown, size, color or style.text_color, _clamp(visible), anchor, **kw)

    single = "\n" not in text and bool(text) and face.measure(text) <= wrap
    arrival = p if not previous else _clamp((p - 0.3) / 0.7)
    letters_in = single and motion in LETTER_MOTIONS and p < 1.0 and not exiting
    leaving = ease(style.easing, _clamp(p / (0.45 if text else 0.7)))  # how far the old name has left
    if single and (letters_in or effect in _LETTER_EFFECTS):
        if previous:
            put(previous, 1 - _clamp(leaving), 0.0)
        _draw_letters(canvas, text, face, style, lay, text_y, base_size, cycle, effect, pulse, arrival, letters_in, scale, emit)
        return

    arriving = ease(style.easing, arrival)
    if effect == "pulse" and style.shape == "plain":
        put(text, 1.0, 0.0, color=blend(style.text_color, style.accent, pulse * accent_level))
    elif motion == "type":
        put(text, 1.0, 0.0, reveal=arriving)
    else:
        if motion != "none":
            put(previous, 1 - _clamp(leaving), leaving, 1 + 0.15 * leaving if motion == "zoom" else 1.0)
        put(
            text, 1.0 if motion == "none" else _clamp(arriving), arriving - 1,
            0.75 + 0.25 * arriving if motion == "zoom" else 1.0,
        )


def _draw_letters(
    canvas: tk.Canvas, text: str, face: tkfont.Font, style: TitleStyle, lay: Layout, text_y: float, base_size: int,
    cycle: float, effect: str, pulse: float, arrival: float, in_motion: bool, scale: float, emit,
) -> None:
    """The name one letter at a time, so each can have its own colour, height and entrance."""
    count = len(text)
    colors = _letter_colors(effect, count, cycle, style) if effect in _LETTER_EFFECTS else [style.text_color] * count
    shown, dys, visible = list(text), [0.0] * count, [1.0] * count
    if in_motion:
        travel = _TRAVEL_PX.get(style.motion, 0) * scale
        for i, letter in enumerate(text):
            local = _clamp(arrival * (1 + _STAGGER) - i / count * _STAGGER)
            e = ease(style.easing, local)
            visible[i] = _clamp(e if style.motion == "letters_fade" else local * 1.6)
            if style.motion == "letters_rise":
                dys[i] = travel * (1 - e)
            elif style.motion == "letters_drop":
                dys[i] = -travel * (1 - e)
            elif style.motion == "scramble" and local < 1.0 and letter != " ":
                shown[i] = random.Random(i * 7919 + int(arrival * 40)).choice(_SCRAMBLE)
                colors[i] = blend(blend(style.text_color, style.accent, style.accent_opacity / 100), style.text_color, local)
                visible[i] = 1.0
    if effect == "wave":
        amplitude = 0.10 * base_size
        for i in range(count):
            dys[i] -= amplitude * math.sin(2 * math.pi * (cycle - (i + 0.5) / count * 1.2))
    left = lay.text_x - face.measure(text) / 2
    glow = (0.35 + 0.65 * pulse) if effect == "glow" else 0.0
    for i, letter in enumerate(text):
        if letter == " ":
            continue
        centre = left + face.measure(text[:i]) + face.measure(letter) / 2
        emit(centre, text_y + dys[i], shown[i], base_size, colors[i], visible[i], "center", glow)
