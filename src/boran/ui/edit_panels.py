from __future__ import annotations

import tkinter as tk
from typing import Callable

from PIL import Image, ImageOps, ImageTk

from boran.edits import ADJUSTMENTS, LOOKS, Edits, apply
from boran.ui import fonts, theme
from boran.ui.slider import AdjustSlider

_THUMB = 80
_COLUMNS = 3
_PAD = 14

# Panels never hold their own copy of the edits: they ask the app to transform the active photo's edits.
Update = Callable[[Callable[[Edits], Edits]], None]


def _button(parent: tk.Widget, text: str, press: Callable[[], None], release: Callable[[], None] | None = None) -> tk.Label:
    """A flat button; `release` (optional) also fires when the mouse button comes up, for hold-style actions."""
    label = tk.Label(
        parent, text=text, bg=theme.BUTTON, fg=theme.FG, font=(fonts.family(), 9), padx=10, pady=6, cursor="hand2"
    )
    label.bind("<Enter>", lambda _e: label.configure(bg=theme.BUTTON_HOVER))
    label.bind("<Leave>", lambda _e: label.configure(bg=theme.BUTTON))
    label.bind("<ButtonPress-1>", lambda _e: press())
    if release is not None:
        label.bind("<ButtonRelease-1>", lambda _e: release())
    return label


class AdjustPanel:
    """Sliders for light, colour, detail and effects, plus compare and reset."""

    def __init__(self, parent: tk.Frame, update: Update, on_compare: Callable[[bool], None], on_reset: Callable[[], None]) -> None:
        self._update = update
        self._enabled = False
        self._sliders: dict[str, AdjustSlider] = {}
        self._note = tk.Label(
            parent, text="Open a photo to adjust it.", bg=theme.PANEL, fg=theme.MUTED, font=(fonts.family(), 9),
            anchor="w", justify="left",
        )
        group = ""
        self._first: tk.Widget | None = None
        for adj in ADJUSTMENTS:
            if adj.group != group:
                group = adj.group
                heading = tk.Label(
                    parent, text=group.upper(), bg=theme.PANEL, fg=theme.MUTED, font=(fonts.family(), 8, "bold"), anchor="w"
                )
                heading.pack(fill="x", padx=_PAD, pady=(14, 0))
                self._first = self._first or heading
            slider = AdjustSlider(parent, adj.label, adj.low, adj.high, lambda v, k=adj.key: self._changed(k, v))
            slider.pack(fill="x", padx=_PAD)
            self._sliders[adj.key] = slider
        row = tk.Frame(parent, bg=theme.PANEL)
        row.pack(fill="x", padx=_PAD, pady=(18, 16))
        _button(row, "Hold to compare", lambda: on_compare(True), lambda: on_compare(False)).pack(side="left")
        _button(row, "Reset all", on_reset).pack(side="right")
        self.load(None)

    def load(self, edits: Edits | None) -> None:
        self._enabled = edits is not None
        for key, slider in self._sliders.items():
            slider.set(edits.value(key) if edits else 0)
            slider.set_enabled(edits is not None)
        if edits is None:
            self._note.pack(fill="x", padx=_PAD, pady=(10, 0), before=self._first)
        else:
            self._note.pack_forget()

    def _changed(self, key: str, value: int) -> None:
        if self._enabled:
            self._update(lambda edits: edits.with_adjust(key, value))


class LooksPanel:
    """Preset looks shown as thumbnails of the current photo, with an intensity slider."""

    def __init__(self, parent: tk.Frame, update: Update) -> None:
        self._parent = parent
        self._update = update
        self._enabled = False
        self._image: Image.Image | None = None
        self._thumbs_for: Image.Image | None = None
        self._photos: dict[str, ImageTk.PhotoImage] = {}
        self._blank = tk.PhotoImage(master=parent, width=_THUMB, height=_THUMB)  # keeps the cells square until rendered
        self._cells: dict[str, tk.Frame] = {}
        self._note = tk.Label(
            parent, text="Open a photo to try looks on it.", bg=theme.PANEL, fg=theme.MUTED, font=(fonts.family(), 9),
            anchor="w",
        )
        self._amount = AdjustSlider(parent, "Intensity", 0, 100, self._set_amount, default=100)
        self._amount.pack(fill="x", padx=_PAD, pady=(10, 0))
        self._grid = tk.Frame(parent, bg=theme.PANEL)
        self._grid.pack(fill="x", padx=_PAD - 4, pady=(8, 16))
        for index, (name, look) in enumerate(LOOKS.items()):
            cell = tk.Frame(self._grid, bg=theme.PANEL, highlightthickness=2, highlightbackground=theme.PANEL, cursor="hand2")
            cell.grid(row=index // _COLUMNS, column=index % _COLUMNS, padx=3, pady=3)
            picture = tk.Label(cell, bg=theme.CANVAS, image=self._blank)
            picture.pack()
            tk.Label(cell, text=look.label, bg=theme.PANEL, fg=theme.FG, font=(fonts.family(), 8)).pack(pady=(2, 3))
            for widget in (cell, picture, *cell.winfo_children()):
                widget.bind("<ButtonRelease-1>", lambda _e, n=name: self._pick(n))
            self._cells[name] = cell
        self.load(None, None)

    def load(self, edits: Edits | None, image: Image.Image | None) -> None:
        self._enabled = edits is not None
        self._image = image
        self._amount.set(edits.amount if edits else 100)
        self._amount.set_enabled(edits is not None and edits.look != "original")
        if edits is None:
            self._note.pack(fill="x", padx=_PAD, pady=(10, 0), before=self._amount)
        else:
            self._note.pack_forget()
        self._mark(edits.look if edits else "")

    def ensure_thumbnails(self) -> None:
        """Render every look on a small copy of the photo; done only when the panel is on screen."""
        if self._image is None or self._thumbs_for is self._image:
            return
        proxy = self._image.convert("RGB")
        proxy.thumbnail((256, 256), Image.Resampling.BILINEAR)
        square = ImageOps.fit(proxy, (_THUMB, _THUMB), Image.Resampling.BILINEAR)
        for name, cell in self._cells.items():
            photo = ImageTk.PhotoImage(apply(square, Edits(look=name)))
            self._photos[name] = photo
            cell.winfo_children()[0].configure(image=photo, width=_THUMB, height=_THUMB)
        self._thumbs_for = self._image

    def _mark(self, selected: str) -> None:
        for name, cell in self._cells.items():
            cell.configure(highlightbackground=theme.ACCENT if name == selected else theme.PANEL)

    def _pick(self, name: str) -> None:
        if not self._enabled:
            return
        self._mark(name)
        self._amount.set_enabled(name != "original")
        self._update(lambda edits: edits.with_look(name))

    def _set_amount(self, value: int) -> None:
        if self._enabled:
            self._update(lambda edits: edits.with_look(edits.look, value))
