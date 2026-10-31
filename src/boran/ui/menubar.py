from __future__ import annotations

import tkinter as tk
from typing import Callable

from boran.ui import theme
from boran.ui.darkmenu import DarkMenu
from boran.ui.ribbon import icons_available


def popup(menu: DarkMenu, x: int, y: int) -> None:
    """Show a menu at screen position (x, y); returns when it closes."""
    menu.tk_popup(x, y)


class MenuBar(tk.Frame):
    """Dark File / Faces / View / Help strip that also acts as the window's title bar."""

    def __init__(self, master):
        super().__init__(master, bg=theme.BG)
        self._maximize_label: tk.Label | None = None

    def add_window_controls(
        self, minimize: Callable[[], None], maximize: Callable[[], None], close: Callable[[], None]
    ) -> None:
        """Right-aligned minimise / maximise / close buttons; call before packing anything else on the right."""
        icons = icons_available(self)
        font = (theme.ICON_FAMILY, 9) if icons else theme.TOOLBAR_FONT

        def make(glyph: str, fallback: str, command: Callable[[], None], hover_bg: str) -> tk.Label:
            label = tk.Label(self, text=glyph if icons else fallback, font=font, fg=theme.FG, bg=theme.BG, width=5)
            label.pack(side="right", fill="y")
            label.bind("<Enter>", lambda _e: label.configure(bg=hover_bg))
            label.bind("<Leave>", lambda _e: label.configure(bg=theme.BG))
            label.bind("<ButtonRelease-1>", lambda _e: command())
            return label

        make("\uE8BB", "\u2715", close, "#c42b1c")
        self._maximize_label = make("\uE922", "\u2610", maximize, theme.BUTTON_HOVER)
        make("\uE921", "\u2014", minimize, theme.BUTTON_HOVER)

    def set_maximized(self, maximized: bool) -> None:
        if self._maximize_label is not None:
            glyphs = ("\uE923", "\u2750") if maximized else ("\uE922", "\u2610")
            self._maximize_label.configure(text=glyphs[0] if icons_available(self) else glyphs[1])

    def add_menu(self, title: str) -> DarkMenu:
        menu = DarkMenu(self, font=theme.MENU_FONT)
        label = tk.Label(self, text=title, font=theme.MENU_FONT, fg=theme.FG, bg=theme.BG, padx=10, pady=4)
        label.pack(side="left")
        label.bind("<Enter>", lambda _e: label.configure(bg=theme.BUTTON_HOVER))
        label.bind("<Leave>", lambda _e: label.configure(bg=theme.BG))
        label.bind("<ButtonPress-1>", lambda _e: self._open(label, menu))
        return menu

    @staticmethod
    def _open(label: tk.Label, menu: DarkMenu) -> None:
        label.configure(bg=theme.CHECKED)
        try:
            popup(menu, label.winfo_rootx(), label.winfo_rooty() + label.winfo_height())
        finally:
            label.configure(bg=theme.BG)
