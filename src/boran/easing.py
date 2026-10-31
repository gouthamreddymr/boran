from __future__ import annotations

import math


def _ease_out_bounce(t: float) -> float:
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def _ease_out_back(t: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _ease_out_elastic(t: float) -> float:
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


EASINGS = {
    "linear": lambda t: t,
    "ease-in": lambda t: t**3,
    "ease-out": lambda t: 1 - (1 - t) ** 3,
    "ease-in-out": lambda t: 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
    "sine": lambda t: -(math.cos(math.pi * t) - 1) / 2,
    "expo-out": lambda t: 1.0 if t >= 1 else 1 - 2 ** (-10 * t),
    "back-out": _ease_out_back,
    "bounce-out": _ease_out_bounce,
    "elastic-out": _ease_out_elastic,
}


def ease(name: str, t: float) -> float:
    """Map linear progress `t` (clamped to 0..1) through the named curve. Some curves overshoot 1 on the way."""
    return EASINGS.get(name, EASINGS["ease-out"])(min(1.0, max(0.0, t)))
