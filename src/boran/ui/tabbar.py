from __future__ import annotations

import tkinter as tk
from typing import Callable

from boran.ui import system, theme

_MAX_TITLE = 26


def _shorten(title: str) -> str:
    return title if len(title) <= _MAX_TITLE else title[: _MAX_TITLE - 1] + "\u2026"


class _Tab:
    def __init__(self, bar: "TabBar", uid: int, title: str):
        self.uid, self.title = uid, title
        self.active = False
        self.frame = tk.Frame(bar, bg=theme.BG, cursor="hand2")
        self.accent = tk.Frame(self.frame, height=2, bg=theme.BG)
        self.accent.pack(side="top", fill="x")
        row = tk.Frame(self.frame, bg=theme.BG)
        row.pack(side="top")
        self.row = row
        self.label = tk.Label(row, text=_shorten(title), font=theme.TOOLBAR_FONT, fg=theme.MUTED, bg=theme.BG, padx=10, pady=6)
        self.label.pack(side="left")
        self.close = tk.Label(row, text="\u2715", font=(theme.SYSTEM_FONT, 8), fg=theme.MUTED, bg=theme.BG, padx=6, pady=6, cursor="hand2")
        self.close.pack(side="left", padx=(0, 4))

        for w in (self.frame, self.accent, row, self.label):
            w.bind("<ButtonPress-1>", lambda _e: bar.on_select(uid))
            w.bind(f"<ButtonPress-{system.MIDDLE_BUTTON}>", lambda _e: bar.on_close(uid))
            w.bind("<Enter>", lambda _e: self.paint(hover=True))
            w.bind("<Leave>", lambda _e: self.paint(hover=False))
        self.close.bind("<ButtonPress-1>", lambda _e: bar.on_close(uid))
        self.close.bind("<Enter>", lambda _e: self.close.configure(fg="white", bg="#c42b1c"))
        self.close.bind("<Leave>", lambda _e: self.close.configure(fg=theme.FG if self.active else theme.MUTED, bg=self._bg()))

    def _bg(self, hover: bool = False) -> str:
        return theme.PANEL if self.active else (theme.TAB_HOVER if hover else theme.BG)

    def paint(self, hover: bool = False) -> None:
        bg = self._bg(hover)
        for w in (self.frame, self.row):
            w.configure(bg=bg)
        self.accent.configure(bg=theme.ACCENT if self.active else bg)
        self.label.configure(bg=bg, fg=theme.FG if self.active else theme.MUTED)
        self.close.configure(bg=bg, fg=theme.FG if self.active else theme.MUTED)


class TabBar(tk.Frame):
    """Photoshop-style document tabs."""

    def __init__(self, master):
        super().__init__(master, bg=theme.BG)
        self.on_select: Callable[[int], None] = lambda uid: None
        self.on_close: Callable[[int], None] = lambda uid: None
        self._tabs: list[_Tab] = []

    def _find(self, uid: int) -> _Tab | None:
        return next((t for t in self._tabs if t.uid == uid), None)

    def add(self, uid: int, title: str) -> None:
        tab = _Tab(self, uid, title)
        tab.frame.pack(side="left")
        self._tabs.append(tab)

    def replace(self, old_uid: int, new_uid: int, title: str) -> None:
        """Swap a tab's document without moving the tab."""
        tab = self._find(old_uid)
        if tab is None:
            self.add(new_uid, title)
            return
        tab.frame.destroy()
        index = self._tabs.index(tab)
        new = _Tab(self, new_uid, title)
        self._tabs[index] = new
        for t in self._tabs:
            t.frame.pack_forget()
        for t in self._tabs:
            t.frame.pack(side="left")

    def remove(self, uid: int) -> None:
        tab = self._find(uid)
        if tab is not None:
            tab.frame.destroy()
            self._tabs.remove(tab)

    def select(self, uid: int) -> None:
        for t in self._tabs:
            t.active = t.uid == uid
            t.paint()

    def set_title(self, uid: int, title: str) -> None:
        tab = self._find(uid)
        if tab is not None and tab.title != title:
            tab.title = title
            tab.label.configure(text=_shorten(title))
