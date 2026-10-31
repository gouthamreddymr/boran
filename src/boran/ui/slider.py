from __future__ import annotations

import tkinter as tk
from typing import Callable

from boran.ui import fonts, theme

_HEIGHT = 46
_TRACK_Y = 34
_HANDLE = 7  # handle radius
_SIDE = _HANDLE + 2


class AdjustSlider(tk.Canvas):
    """Lightroom-style slider: label and value on top, a thin track below. Double-click resets it."""

    def __init__(
        self, master, label: str, low: int, high: int, command: Callable[[int], None], default: int = 0, **kw
    ) -> None:
        super().__init__(master, height=_HEIGHT, bg=theme.PANEL, highlightthickness=0, **kw)
        self._label, self._low, self._high, self._default = label, low, high, default
        self._command = command
        self._value = default
        self._enabled = True
        self._font = (fonts.family(), 9)
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<ButtonPress-1>", self._on_drag)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Double-Button-1>", self._on_reset)

    @property
    def value(self) -> int:
        return self._value

    def set(self, value: int) -> None:
        """Move the slider without calling the command."""
        self._value = max(self._low, min(self._high, int(value)))
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="" if enabled else "arrow")
        self._draw()

    def _x_of(self, value: float) -> float:
        width = max(1, self.winfo_width() - 2 * _SIDE)
        return _SIDE + (value - self._low) / (self._high - self._low) * width

    def _draw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 1:
            return
        active = self._enabled and self._value != self._default
        fg = theme.FG if self._enabled else theme.DISABLED
        self.create_text(2, 12, text=self._label, anchor="w", fill=fg, font=self._font)
        self.create_text(
            width - 2, 12, text=str(self._value), anchor="e", fill=theme.ACCENT if active else theme.MUTED, font=self._font
        )
        left, right, y = _SIDE, width - _SIDE, _TRACK_Y
        self.create_line(left, y, right, y, fill=theme.BUTTON_HOVER, width=3, capstyle="round")
        origin = self._x_of(self._default)
        x = self._x_of(self._value)
        if self._enabled and x != origin:
            self.create_line(origin, y, x, y, fill=theme.ACCENT, width=3, capstyle="round")
        self.create_line(origin, y - 4, origin, y + 4, fill=theme.MUTED if self._low < 0 else theme.BUTTON_HOVER)
        knob = "#ffffff" if self._enabled else theme.DISABLED
        self.create_oval(x - _HANDLE, y - _HANDLE, x + _HANDLE, y + _HANDLE, fill=knob, outline=theme.PANEL, width=2)

    def _on_drag(self, event) -> None:
        if not self._enabled:
            return
        width = max(1, self.winfo_width() - 2 * _SIDE)
        fraction = min(1.0, max(0.0, (event.x - _SIDE) / width))
        value = round(self._low + fraction * (self._high - self._low))
        if abs(value - self._default) <= 1:  # a little magnet at the neutral point
            value = self._default
        if value != self._value:
            self._value = value
            self._draw()
            self._command(value)

    def _on_reset(self, _event) -> None:
        if self._enabled and self._value != self._default:
            self._value = self._default
            self._draw()
            self._command(self._value)
