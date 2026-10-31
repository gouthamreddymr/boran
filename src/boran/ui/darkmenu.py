from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from boran.ui import frameless, theme

_MIN_WIDTH = 230
_CHECK = "\u2713"


class DarkMenu:
    """A dark drop-down menu drawn with Tk widgets.

    Native Windows popup menus always carry a light 3 px frame, so this mirrors the small part of the `tk.Menu`
    API the app uses (`add_command`, `add_checkbutton`, `add_separator`, `index`, `entryconfigure`, `tk_popup`).
    """

    def __init__(self, master: tk.Misc, font=theme.MENU_FONT) -> None:
        self._master = master.winfo_toplevel()
        self._font = font
        self._entries: list[dict[str, Any]] = []
        self._win: tk.Toplevel | None = None
        self._rows: list[dict[str, tk.Widget] | None] = []
        self._active: int | None = None
        self._chosen: int | None = None

    # --- building ---------------------------------------------------------
    def add_command(self, label: str = "", command: Callable[[], None] | None = None, accelerator: str = "", **_: Any) -> None:
        self._entries.append({"kind": "command", "label": label, "command": command, "accelerator": accelerator})

    def add_checkbutton(
        self, label: str = "", command: Callable[[], None] | None = None, accelerator: str = "",
        variable: tk.Variable | None = None, **_: Any,
    ) -> None:
        self._entries.append(
            {"kind": "checkbutton", "label": label, "command": command, "accelerator": accelerator, "variable": variable}
        )

    def add_separator(self) -> None:
        self._entries.append({"kind": "separator"})

    def index(self, which: int | str) -> int:
        """Position of an entry; "end" is the last one (-1 while the menu is empty)."""
        return len(self._entries) - 1 if which == "end" else int(which)

    def entryconfigure(self, index: int, **options: Any) -> None:
        """Accepts `foreground`, `activeforeground` and `activebackground`; other options are ignored."""
        self._entries[index].update({k: v for k, v in options.items() if k in _STYLE_KEYS})

    def invoke(self, index: int) -> None:
        entry = self._entries[index]
        if entry["kind"] == "separator":
            return
        variable = entry.get("variable")
        if entry["kind"] == "checkbutton" and variable is not None:
            variable.set(not variable.get())
        command = entry.get("command")
        if command is not None:
            command()

    # --- showing ----------------------------------------------------------
    def tk_popup(self, x: int, y: int) -> None:
        """Show the menu at screen position (x, y); returns once it closes and any chosen command has run."""
        if self._win is not None or not self._entries:
            return
        self._chosen = None
        win = self._build()
        self._win = win
        try:
            win.update_idletasks()
            width, height = win.winfo_reqwidth(), win.winfo_reqheight()
            x = max(0, min(x, win.winfo_screenwidth() - width))
            y = max(0, min(y, win.winfo_screenheight() - height))
            win.geometry(f"+{x}+{y}")
            win.deiconify()
            frameless.round_corners(win)
            win.wait_visibility()
            win.grab_set()
            win.focus_force()
            win.wait_window()
        finally:
            self._win = None
            self._rows = []
            self._active = None
        if self._chosen is not None:
            self.invoke(self._chosen)

    def grab_release(self) -> None:
        """Kept for tk.Menu compatibility; the grab is released when the menu closes."""

    def unpost(self) -> None:
        self._close()

    def _close(self) -> None:
        win, self._win = self._win, None
        if win is not None:
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()

    def _build(self) -> tk.Toplevel:
        win = tk.Toplevel(self._master)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=theme.BORDER)
        body = tk.Frame(win, bg=theme.PANEL)
        body.pack(padx=1, pady=1)
        tk.Frame(body, width=_MIN_WIDTH, height=4, bg=theme.PANEL).pack()  # fixes the minimum width and top padding
        self._rows = []
        for i, entry in enumerate(self._entries):
            if entry["kind"] == "separator":
                tk.Frame(body, height=1, bg=theme.BORDER).pack(fill="x", padx=10, pady=4)
                self._rows.append(None)
                continue
            row = tk.Frame(body, bg=theme.PANEL)
            row.pack(fill="x")
            variable = entry.get("variable")
            checked = entry["kind"] == "checkbutton" and variable is not None and bool(variable.get())
            check = tk.Label(row, text=_CHECK if checked else "", width=3, font=self._font, anchor="center")
            label = tk.Label(row, text=entry["label"], font=self._font, anchor="w")
            accel = tk.Label(row, text=entry.get("accelerator", ""), font=self._font, anchor="e")
            check.pack(side="left", pady=5)
            label.pack(side="left", fill="x", expand=True, pady=5)
            accel.pack(side="right", padx=(24, 14), pady=5)
            widgets = {"row": row, "check": check, "label": label, "accel": accel}
            self._rows.append(widgets)
            for widget in widgets.values():
                widget.bind("<Enter>", lambda _e, i=i: self._set_active(i))
                widget.bind("<ButtonRelease-1>", lambda _e, i=i: self._choose(i))
        tk.Frame(body, height=4, bg=theme.PANEL).pack()
        for i in range(len(self._rows)):
            self._paint(i)
        win.bind("<ButtonPress>", self._on_press)
        win.bind("<Escape>", lambda _e: self._close())
        win.bind("<Up>", lambda _e: self._step(-1))
        win.bind("<Down>", lambda _e: self._step(1))
        win.bind("<Return>", lambda _e: self._active is not None and self._choose(self._active))
        win.bind("<FocusOut>", self._on_focus_out)
        return win

    # --- interaction ------------------------------------------------------
    def _on_press(self, event: tk.Event) -> None:
        """Clicks outside the menu (delivered here because of the grab) dismiss it."""
        win = self._win
        if win is None:
            return
        inside = (
            win.winfo_rootx() <= event.x_root < win.winfo_rootx() + win.winfo_width()
            and win.winfo_rooty() <= event.y_root < win.winfo_rooty() + win.winfo_height()
        )
        if not inside:
            self._close()

    def _on_focus_out(self, event: tk.Event) -> None:
        win = self._win
        if win is not None and event.widget is win and win.focus_displayof() is None:
            self._close()

    def _choose(self, index: int) -> None:
        if not self._is_selectable(index):
            return
        self._chosen = index
        self._close()

    def _is_selectable(self, index: int) -> bool:
        entry = self._entries[index]
        return entry["kind"] != "separator" and entry.get("activebackground", theme.MENU_ACTIVE) != theme.PANEL

    def _set_active(self, index: int | None) -> None:
        previous, self._active = self._active, index
        for i in (previous, index):
            if i is not None and i < len(self._rows):
                self._paint(i)

    def _step(self, delta: int) -> None:
        count = len(self._entries)
        index = self._active if self._active is not None else (count if delta > 0 else -1)
        for _ in range(count):
            index = (index + delta) % count
            if self._is_selectable(index):
                self._set_active(index)
                return

    def _paint(self, index: int) -> None:
        widgets = self._rows[index]
        if widgets is None:
            return
        entry = self._entries[index]
        hovered = index == self._active
        if hovered:
            bg = entry.get("activebackground", theme.MENU_ACTIVE)
            fg = entry.get("activeforeground", "white")
            accel_fg = fg if bg == theme.PANEL else "#cfd3dc"
        else:
            bg = theme.PANEL
            fg = entry.get("foreground", theme.FG)
            accel_fg = theme.DISABLED if fg == theme.DISABLED else theme.MUTED
        for key, widget in widgets.items():
            widget.configure(bg=bg)
            if key != "row":
                widget.configure(fg=accel_fg if key == "accel" else fg)


_STYLE_KEYS = ("foreground", "activeforeground", "activebackground")
