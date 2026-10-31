from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from boran.ui import theme

MAX_NAME_LEN = 100


def ask_name(parent: tk.Misc, current: str, known: set[str]) -> str | None:
    """Modal name prompt with filter-as-you-type suggestions. None means cancelled."""
    choices = sorted(known | ({current} if current else set()), key=str.lower)
    result: list[str | None] = [None]

    dlg = tk.Toplevel(parent, bg=theme.BG)
    dlg.title("Name this person")
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)

    frame = ttk.Frame(dlg, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Name (leave empty to clear):", style="Dialog.TLabel").pack(anchor="w")
    var = tk.StringVar(value=current)
    box = ttk.Combobox(frame, textvariable=var, values=choices, width=34, style="Dialog.TCombobox", font=theme.DIALOG_FONT)
    box.pack(fill="x", pady=(4, 10))

    def accept(_event=None) -> None:
        result[0] = var.get().strip()[:MAX_NAME_LEN]
        dlg.destroy()

    def narrow(event) -> None:
        if event.keysym in ("Return", "Escape", "Up", "Down", "Tab"):
            return
        text = var.get().strip().lower()
        box["values"] = [c for c in choices if text in c.lower()] or choices

    row = ttk.Frame(frame)
    row.pack(anchor="e")
    ttk.Button(row, text="OK", command=accept, style="Dialog.TButton").pack(side="left", padx=(0, 6))
    ttk.Button(row, text="Cancel", command=dlg.destroy, style="Dialog.TButton").pack(side="left")

    box.bind("<KeyRelease>", narrow)
    dlg.bind("<Return>", accept)
    dlg.bind("<Escape>", lambda _e: dlg.destroy())

    dlg.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - dlg.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    theme.dark_titlebar(dlg)

    box.focus_set()
    box.select_range(0, "end")
    dlg.grab_set()
    dlg.wait_window()
    return result[0]
