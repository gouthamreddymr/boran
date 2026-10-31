from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable

from boran.ui import theme

_icons_ok: bool | None = None


def icons_available(root: tk.Misc) -> bool:
    """True if the Windows icon font is installed (Segoe MDL2 Assets ships with Windows 10 and 11)."""
    global _icons_ok
    if _icons_ok is None:
        _icons_ok = theme.ICON_FAMILY in tkfont.families(root)
    return _icons_ok


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 500, side: str = "below"):
        self._widget, self._text, self._delay, self._side = widget, text, delay_ms, side
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        for w in (widget, *widget.winfo_children()):
            w.bind("<Enter>", self._schedule, add="+")
            w.bind("<Leave>", self._hide, add="+")
            w.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        if self._job is None and self._tip is None:
            self._job = self._widget.after(self._delay, self._show)

    def _show(self) -> None:
        self._job = None
        tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        w = self._widget
        label = tk.Label(
            tip, text=self._text, font=theme.TOOLBAR_FONT, bg=theme.BUTTON, fg=theme.FG,
            padx=8, pady=4, highlightthickness=1, highlightbackground=theme.BORDER,
        )
        label.pack()
        if self._side == "right":
            x, y = w.winfo_rootx() + w.winfo_width() + 6, w.winfo_rooty() + 4
        elif self._side == "left":
            x, y = w.winfo_rootx() - label.winfo_reqwidth() - 6, w.winfo_rooty() + 4
        else:
            x, y = w.winfo_rootx(), w.winfo_rooty() + w.winfo_height() + 4
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None) -> None:
        if self._job is not None:
            self._widget.after_cancel(self._job)
            self._job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class RibbonButton(tk.Frame):
    """Icon-over-label command button; with `var` it behaves as a toggle."""

    def __init__(
        self, master, text: str, command: Callable[[], None], icon: str = "", *,
        var: tk.BooleanVar | None = None, tip: str | None = None, compact: bool = False, text_icon: bool = False,
        tip_side: str = "below",
    ):
        super().__init__(master, bg=theme.PANEL, cursor="hand2")
        self._command, self._var = command, var
        self._hover = self._pressed = self._disabled = False
        self._labels: list[tk.Label] = []

        show_icon = bool(icon) and (text_icon or icons_available(self))
        pad = 6 if compact else 10
        if show_icon:
            font = theme.TOOLBAR_FONT_BOLD if text_icon else (theme.ICON_FAMILY, 13 if compact else 16)
            self._add_label(icon, font, padx=pad, pady=(6, 0 if not compact else 6))
        if text and (not compact or not show_icon):
            self._add_label(text, theme.RIBBON_FONT if not compact else theme.TOOLBAR_FONT, padx=pad,
                            pady=(0 if show_icon else 6, 6))

        for w in (self, *self._labels):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<ButtonPress-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
        if var is not None:
            var.trace_add("write", lambda *_: self._paint())
        if tip:
            Tooltip(self, tip, side=tip_side)
        self._paint()

    def _add_label(self, text: str, font, padx: int, pady) -> None:
        label = tk.Label(self, text=text, font=font, bg=theme.PANEL, fg=theme.FG)
        label.pack(padx=padx, pady=pady)
        self._labels.append(label)

    # --- ttk-style state API ---------------------------------------------
    def state(self, spec: list[str]) -> None:
        if "disabled" in spec:
            self._disabled = True
        elif "!disabled" in spec:
            self._disabled = False
        self.configure(cursor="arrow" if self._disabled else "hand2")
        self._paint()

    def instate(self, spec: list[str]) -> bool:
        return self._disabled if "disabled" in spec else not self._disabled

    # --- behaviour --------------------------------------------------------
    def _inside(self) -> bool:
        try:
            under = self.winfo_containing(*self.winfo_pointerxy())
        except (KeyError, tk.TclError):
            return False
        return under is not None and (under is self or str(under).startswith(str(self) + "."))

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._paint()

    def _on_leave(self, _event) -> None:
        if not self._inside():
            self._hover = self._pressed = False
            self._paint()

    def _on_press(self, _event) -> None:
        if not self._disabled:
            self._pressed = True
            self._paint()

    def _on_release(self, _event) -> None:
        fire = self._pressed and self._inside() and not self._disabled
        self._pressed = False
        self._paint()
        if fire:
            if self._var is not None:
                self._var.set(not self._var.get())
            self._command()

    def _paint(self) -> None:
        checked = self._var is not None and bool(self._var.get())
        if self._disabled:
            bg, fg = theme.PANEL, theme.DISABLED
        elif self._pressed:
            bg, fg = theme.PRESSED, "white"
        elif checked:
            bg, fg = theme.CHECKED, "white"
        elif self._hover:
            bg, fg = theme.BUTTON_HOVER, theme.FG
        else:
            bg, fg = theme.PANEL, theme.FG
        self.configure(bg=bg)
        for label in self._labels:
            label.configure(bg=bg, fg=fg)


class RibbonGroup(tk.Frame):
    def __init__(self, master, title: str, compact: bool = False):
        super().__init__(master, bg=theme.PANEL)
        self._compact = compact
        self._body = tk.Frame(self, bg=theme.PANEL)
        self._body.pack(side="top")
        if not compact:
            tk.Label(self, text=title, font=theme.RIBBON_FONT, fg=theme.MUTED, bg=theme.PANEL).pack(side="bottom", pady=(2, 3))

    def button(self, text: str, command: Callable[[], None], icon: str = "", **kw) -> RibbonButton:
        b = RibbonButton(self._body, text, command, icon, compact=self._compact, **kw)
        b.pack(side="left", padx=1)
        return b


class Ribbon(tk.Frame):
    """A strip of command groups: captioned like Word's ribbon, or compact and icon-only like Photoshop's options bar."""

    def __init__(self, master, compact: bool = False):
        super().__init__(master, bg=theme.PANEL)
        self._compact = compact
        self._count = 0

    def group(self, title: str) -> RibbonGroup:
        if self._count:
            tk.Frame(self, bg=theme.BORDER, width=1).pack(side="left", fill="y", pady=6 if self._compact else 8)
        self._count += 1
        g = RibbonGroup(self, title, self._compact)
        g.pack(side="left", fill="y", padx=4 if self._compact else 6, pady=(2, 2) if self._compact else (4, 0))
        return g
