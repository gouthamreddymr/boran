from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from boran.ui import fonts, theme
from boran.ui.ribbon import RibbonButton

RAIL_WIDTH = 40
PANEL_WIDTH = 320


class RightDock(tk.Frame):
    """A panel on the right that collapses to an icon rail stuck to the window's right edge.

    Each section has an icon on the rail. Clicking an icon opens that section; clicking the open section's icon (or
    the arrow in the panel header) collapses the panel and leaves only the rail. More sections can be added later
    with `add_section`.
    """

    def __init__(self, master) -> None:
        super().__init__(master, bg=theme.PANEL)
        self.rail = tk.Frame(self, bg=theme.PANEL, width=RAIL_WIDTH)
        self.rail.pack(side="right", fill="y")
        self.rail.pack_propagate(False)
        self._sep = tk.Frame(self, width=1, bg=theme.BORDER)
        self._sep.pack(side="right", fill="y")
        self._panel = tk.Frame(self, bg=theme.PANEL, width=PANEL_WIDTH)
        self._panel.pack_propagate(False)

        head = tk.Frame(self._panel, bg=theme.PANEL)
        head.pack(side="top", fill="x")
        self._title = tk.Label(head, bg=theme.PANEL, fg=theme.FG, font=(fonts.family(), 11, "bold"), anchor="w")
        self._title.pack(side="left", padx=14, pady=10)
        close = tk.Label(head, text="\u00bb", bg=theme.PANEL, fg=theme.MUTED, font=(fonts.family(), 14), cursor="hand2")
        close.pack(side="right", padx=12)
        close.bind("<Enter>", lambda _e: close.configure(fg=theme.FG))
        close.bind("<Leave>", lambda _e: close.configure(fg=theme.MUTED))
        close.bind("<ButtonRelease-1>", lambda _e: self.hide())
        tk.Frame(self._panel, height=1, bg=theme.BORDER).pack(side="top", fill="x")
        self._body = tk.Frame(self._panel, bg=theme.PANEL)
        self._body.pack(side="top", fill="both", expand=True)

        self._sections: dict[str, tuple[tk.Widget, str, tk.BooleanVar, tk.Canvas, tk.Frame]] = {}
        self._active: str | None = None
        self._last: str | None = None
        self._open = False
        self.on_change: Callable[[bool, str | None], None] = lambda opened, section: None
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _on_wheel(self, event) -> None:
        """Scroll the open section when the pointer is over the panel."""
        if not self._open or self._active is None:
            return
        under = self.winfo_containing(event.x_root, event.y_root)
        if under is None or not str(under).startswith(str(self._panel)):
            return
        canvas, content = self._sections[self._active][3:]
        if content.winfo_reqheight() > canvas.winfo_height():
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def active(self) -> str | None:
        return self._active

    def add_section(self, key: str, icon: str, title: str, tip: str) -> tk.Frame:
        """Add a rail icon and return the (scrollable) frame to fill with that section's controls."""
        holder = tk.Frame(self._body, bg=theme.PANEL)
        canvas = tk.Canvas(holder, bg=theme.PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview, style="Vertical.TScrollbar")
        content = tk.Frame(canvas, bg=theme.PANEL)
        window = canvas.create_window(0, 0, window=content, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        var = tk.BooleanVar(value=False)
        button = RibbonButton(
            self.rail, title, lambda: self._on_rail(key), icon, var=var, compact=True, tip=tip, tip_side="left"
        )
        button.pack(pady=(6 if not self._sections else 2, 2))
        self._sections[key] = (holder, title, var, canvas, content)
        return content

    def show(self, key: str | None = None) -> None:
        key = key or self._last or next(iter(self._sections), None)
        if key not in self._sections:
            return
        if self._active is not None and self._active != key:
            self._sections[self._active][0].pack_forget()
        holder, title = self._sections[key][:2]
        self._title.configure(text=title)
        holder.pack(fill="both", expand=True)
        if not self._open:
            self._panel.pack(side="right", fill="y")
            self._open = True
        self._active = self._last = key
        self._sync_rail()
        self.on_change(True, key)

    def hide(self) -> None:
        if not self._open:
            return
        self._panel.pack_forget()
        self._open = False
        self._sync_rail()
        self.on_change(False, self._active)

    def toggle(self) -> None:
        self.hide() if self._open else self.show()

    def _on_rail(self, key: str) -> None:
        if self._open and self._active == key:
            self.hide()
        else:
            self.show(key)

    def _sync_rail(self) -> None:
        for key, section in self._sections.items():
            section[2].set(self._open and key == self._active)
