from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

_SUPERSAMPLE = 4  # draw large and shrink so the rounded corners are smooth


class Chip(tk.Canvas):
    """A small rounded label, such as a keyboard-shortcut badge."""

    def __init__(self, master, font, fill: str, fg: str, bg: str, radius: int = 5, padx: int = 8, pady: int = 2):
        super().__init__(master, highlightthickness=0, bd=0, bg=bg)
        self._font = tkfont.Font(root=master, font=font)
        self._fill, self._fg, self._radius, self._padx, self._pady = fill, fg, radius, padx, pady
        self._photo: ImageTk.PhotoImage | None = None
        self.set_text("")

    def set_text(self, text: str) -> None:
        width = self._font.measure(text) + 2 * self._padx
        height = self._font.metrics("linespace") + 2 * self._pady
        scale = _SUPERSAMPLE
        big = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        ImageDraw.Draw(big).rounded_rectangle(
            (0, 0, width * scale - 1, height * scale - 1), radius=self._radius * scale, fill=self._fill
        )
        self._photo = ImageTk.PhotoImage(big.resize((width, height), Image.Resampling.LANCZOS))
        self.delete("all")
        self.configure(width=width, height=height)
        self.create_image(0, 0, anchor="nw", image=self._photo)
        self.create_text(width / 2, height / 2 - 1, text=text, font=self._font, fill=self._fg)
