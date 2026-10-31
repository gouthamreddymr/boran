from __future__ import annotations

import tkinter as tk
from collections import deque

from boran.ui import theme
from boran.ui.ribbon import icons_available

MAX_VISIBLE = 3
DURATION_MS = 5000

# kind -> (stripe/icon colour, icon-font glyph, plain-text fallback)
_KINDS = {
    "info": (theme.ACCENT, "\uE946", "i"),
    "success": (theme.SUCCESS, "\uE73E", "\u2713"),
    "warning": (theme.WARNING, "\uE7BA", "!"),
    "error": (theme.ERROR, "\uE783", "\u2715"),
}


class _Snack:
    def __init__(self, host: "SnackbarHost", text: str, kind: str):
        color, glyph, fallback = _KINDS.get(kind, _KINDS["info"])
        parent = host.parent
        self.text = text
        self.job: str | None = None
        self.frame = tk.Frame(parent, bg=theme.SNACK_BG, highlightthickness=1, highlightbackground=theme.BORDER)
        tk.Frame(self.frame, width=4, bg=color).pack(side="left", fill="y")
        icons = icons_available(parent)
        icon = tk.Label(
            self.frame, text=glyph if icons else fallback, fg=color, bg=theme.SNACK_BG,
            font=(theme.ICON_FAMILY, 12) if icons else theme.TOOLBAR_FONT_BOLD,
        )
        icon.pack(side="left", padx=(10, 6), pady=10)
        label = tk.Label(
            self.frame, text=text, fg=theme.FG, bg=theme.SNACK_BG, font=theme.MENU_FONT, justify="left", wraplength=320,
        )
        label.pack(side="left", pady=10)
        close = tk.Label(self.frame, text="\u2715", fg=theme.MUTED, bg=theme.SNACK_BG, font=("Segoe UI", 9), padx=10, cursor="hand2")
        close.pack(side="left", fill="y")
        close.bind("<ButtonRelease-1>", lambda _e: host.dismiss(self))
        close.bind("<Enter>", lambda _e: close.configure(fg=theme.FG))
        close.bind("<Leave>", lambda _e: close.configure(fg=theme.MUTED))
        for widget in (self.frame, icon, label, close):  # hovering keeps it on screen
            widget.bind("<Enter>", lambda _e: host.pause(self), add="+")
            widget.bind("<Leave>", lambda _e: host.resume(self), add="+")


class SnackbarHost:
    """Short-lived messages stacked at the bottom-right of `parent`: five seconds each, at most three at once.

    Anything beyond three waits in a queue and appears as space frees up.
    """

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self._visible: list[_Snack] = []
        self._queue: deque[tuple[str, str]] = deque()

    def show(self, text: str, kind: str = "info") -> None:
        newest = self._queue[-1][0] if self._queue else (self._visible[-1].text if self._visible else None)
        if text == newest:  # don't stack the same message twice in a row
            return
        self._queue.append((text, kind))
        self._pump()

    @property
    def visible_count(self) -> int:
        return len(self._visible)

    @property
    def queued_count(self) -> int:
        return len(self._queue)

    def dismiss(self, snack: _Snack) -> None:
        if snack not in self._visible:
            return
        self._cancel(snack)
        self._visible.remove(snack)
        snack.frame.destroy()
        self._pump()

    def pause(self, snack: _Snack) -> None:
        self._cancel(snack)

    def resume(self, snack: _Snack) -> None:
        if snack not in self._visible:
            return
        try:
            under = snack.frame.winfo_containing(*snack.frame.winfo_pointerxy())
        except (KeyError, tk.TclError):
            under = None
        if under is not None and str(under).startswith(str(snack.frame)):
            return  # still over the snackbar (the pointer only moved between its parts)
        self._arm(snack)

    # --- internals --------------------------------------------------------
    def _pump(self) -> None:
        while self._queue and len(self._visible) < MAX_VISIBLE:
            text, kind = self._queue.popleft()
            snack = _Snack(self, text, kind)
            self._visible.append(snack)
            self._arm(snack)
        self._layout()

    def _arm(self, snack: _Snack) -> None:
        self._cancel(snack)
        snack.job = self.parent.after(DURATION_MS, lambda: self.dismiss(snack))

    def _cancel(self, snack: _Snack) -> None:
        if snack.job is not None:
            self.parent.after_cancel(snack.job)
            snack.job = None

    def _layout(self) -> None:
        offset = 16
        for snack in self._visible:  # oldest at the bottom
            snack.frame.update_idletasks()
            snack.frame.place(relx=1.0, rely=1.0, x=-16, y=-offset, anchor="se")
            snack.frame.lift()
            offset += snack.frame.winfo_reqheight() + 8
