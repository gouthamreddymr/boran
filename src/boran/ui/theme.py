from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from boran.ui import system

BG = "#1e1e1e"
PANEL = "#252526"
CANVAS = "#171717"
BUTTON = "#333337"
BUTTON_HOVER = "#45454b"
BORDER = "#3c3c41"
FG = "#f0f0f0"
MUTED = "#9a9aa4"
DISABLED = "#70707a"
STATUS_FG = "#c4c4cc"
ACCENT = "#4c8dff"
MENU_ACTIVE = "#34415c"  # hovered menu item; white text stays clear and disabled text stays legible
CHECKED = "#2f5597"  # toggled ribbon buttons
PRESSED = "#3a6cc0"
TAB_HOVER = "#2a2a2f"
SNACK_BG = "#2b2b30"
SUCCESS = "#3fb950"
WARNING = "#d29922"
ERROR = "#f85149"

# The top bars (menu, ribbon, tabs) use the system font; everything else uses the app font.
SYSTEM_FONT = "Segoe UI" if system.IS_WIN else ("Helvetica Neue" if system.IS_MAC else "DejaVu Sans")
TOOLBAR_FONT = (SYSTEM_FONT, 9)
MENU_FONT = (SYSTEM_FONT, 10)
TOOLBAR_FONT_BOLD = (SYSTEM_FONT, 11, "bold")
RIBBON_FONT = (SYSTEM_FONT, 8)
ICON_FAMILY = "Segoe MDL2 Assets"
DIALOG_FONT = (SYSTEM_FONT, 10)

_DWMWA_USE_IMMERSIVE_DARK_MODE = (20, 19)  # 19 on older Windows 10 builds


def apply(root: tk.Tk) -> None:
    """Switch all ttk widgets and dropdown lists to the dark palette."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".", background=BG, foreground=FG, fieldbackground=PANEL, troughcolor=PANEL,
        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, focuscolor=BG,
        selectbackground=ACCENT, selectforeground="white", insertcolor=FG,
    )
    style.map(".", foreground=[("disabled", DISABLED)])

    style.configure("TButton", background=BUTTON, foreground=FG, padding=(10, 4))
    style.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", ACCENT), ("active", BUTTON_HOVER)],
        bordercolor=[("focus", ACCENT)],
    )
    style.configure(
        "TCheckbutton", background=BG, foreground=FG, indicatorbackground=PANEL,
        indicatorforeground="white", upperbordercolor=BORDER, lowerbordercolor=BORDER,
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG)],
        indicatorbackground=[("selected", ACCENT), ("disabled", BG)],
    )
    style.configure("TCombobox", background=BUTTON, arrowcolor=FG, padding=4)
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", PANEL)],
        background=[("active", BUTTON_HOVER)],
        bordercolor=[("focus", ACCENT)],
    )
    style.configure("TSeparator", background=BORDER)
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=BUTTON, foreground=MUTED, padding=(14, 6), borderwidth=0, font=DIALOG_FONT)
    style.map(
        "TNotebook.Tab", background=[("selected", PANEL), ("active", BUTTON_HOVER)], foreground=[("selected", FG)]
    )
    style.configure(
        "Horizontal.TProgressbar", background=ACCENT, troughcolor=BUTTON, bordercolor=BUTTON,
        lightcolor=ACCENT, darkcolor=ACCENT,
    )

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, borderwidth=0, rowheight=28)
    style.map(
        "Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", "white")],
    )
    style.configure(
        "Vertical.TScrollbar", background=BUTTON, troughcolor=PANEL, bordercolor=PANEL, arrowcolor=FG,
        lightcolor=BUTTON, darkcolor=BUTTON,
    )
    style.map("Vertical.TScrollbar", background=[("active", BUTTON_HOVER)])

    style.configure("Status.TLabel", background=PANEL, foreground=STATUS_FG, padding=(0, 4))
    style.configure("Dialog.TLabel", font=DIALOG_FONT)
    style.configure("Dialog.TButton", font=DIALOG_FONT)
    style.configure("Dialog.TCombobox", font=DIALOG_FONT)

    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.font", DIALOG_FONT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")


def dark_titlebar(window: tk.Misc) -> None:
    """Ask Windows for a dark title bar on this window; a no-op elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        enabled = ctypes.c_int(1)
        for attribute in _DWMWA_USE_IMMERSIVE_DARK_MODE:
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(enabled), 4) == 0:
                break
    except (AttributeError, OSError):
        pass
