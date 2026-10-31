from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from boran.ui import fonts, theme

PROJECT_URL = "https://github.com/gouthamreddymr/boran"
_ABOUT = "Name the people in your photos.\nFace detection by the Boran Convolutional Neural Engine."


def show_about(parent: tk.Misc) -> None:
    """Modal About box with a button that opens the project page."""
    dlg = tk.Toplevel(parent, bg=theme.BG)
    dlg.title("About Boran")
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)

    frame = ttk.Frame(dlg, padding=18)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="Boran", bg=theme.BG, fg=theme.FG, font=(fonts.family(), 18, "bold")).pack(anchor="w")
    tk.Label(frame, text=_ABOUT, bg=theme.BG, fg=theme.MUTED, font=theme.DIALOG_FONT, justify="left").pack(
        anchor="w", pady=(6, 16)
    )

    def learn_more() -> None:
        if not webbrowser.open(PROJECT_URL):
            dlg.clipboard_clear()
            dlg.clipboard_append(PROJECT_URL)
            status.configure(text="Could not open a browser. The link was copied instead.")

    status = tk.Label(frame, text="", bg=theme.BG, fg=theme.WARNING, font=theme.DIALOG_FONT)
    row = ttk.Frame(frame)
    row.pack(anchor="e")
    ttk.Button(row, text="Learn more about Boran", command=learn_more, style="Dialog.TButton").pack(side="left", padx=(0, 6))
    ttk.Button(row, text="Close", command=dlg.destroy, style="Dialog.TButton").pack(side="left")
    status.pack(anchor="w", pady=(8, 0))

    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.bind("<Return>", lambda _e: dlg.destroy())
    dlg.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - dlg.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    theme.dark_titlebar(dlg)
    dlg.grab_set()
    dlg.wait_window()
