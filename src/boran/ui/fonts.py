from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

_FONT_FILE = Path(__file__).resolve().parent.parent / "fonts" / "GoogleSans-Variable.ttf"
_BUNDLED = "Google Sans"
_FALLBACK = "Segoe UI"
_FR_PRIVATE = 0x10  # font is visible to this process only and is not installed
_NAMED_FONTS = (
    "TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
    "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont",
)

_family = _FALLBACK
_SIZE = 10  # Tk's default 9 pt is small in Google Sans


def family() -> str:
    return _family


def install(root: tk.Misc) -> str:
    """Load the bundled Google Sans for this process and make it the default font everywhere."""
    global _family
    if _register() and _BUNDLED in tkfont.families(root):
        _family = _BUNDLED
    for name in _NAMED_FONTS:
        try:
            tkfont.nametofont(name, root=root).configure(family=_family, size=_SIZE)
        except tk.TclError:
            pass
    return _family


def _register() -> bool:
    if sys.platform != "win32" or not _FONT_FILE.is_file():
        return False
    try:
        import ctypes

        return ctypes.windll.gdi32.AddFontResourceExW(str(_FONT_FILE), _FR_PRIVATE, 0) > 0
    except (AttributeError, OSError):
        return False
