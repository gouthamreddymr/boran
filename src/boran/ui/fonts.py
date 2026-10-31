from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from boran.ui import theme

_FONT_FILE = Path(__file__).resolve().parent.parent / "fonts" / "GoogleSans-Variable.ttf"
_BUNDLED = "Google Sans"
_FALLBACK = theme.SYSTEM_FONT
_FR_PRIVATE = 0x10  # font is visible to this process only and is not installed
_CT_SCOPE_PROCESS = 1  # kCTFontManagerScopeProcess
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
    if not _FONT_FILE.is_file():
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            return ctypes.windll.gdi32.AddFontResourceExW(str(_FONT_FILE), _FR_PRIVATE, 0) > 0
        if sys.platform == "darwin":
            return _register_mac()
    except (AttributeError, OSError):
        pass
    return False


def _register_mac() -> bool:
    import ctypes
    import ctypes.util

    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
    cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
    ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    raw = str(_FONT_FILE).encode()
    url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
    if not url:
        return False
    try:
        return bool(ct.CTFontManagerRegisterFontsForURL(url, _CT_SCOPE_PROCESS, None))
    finally:
        cf.CFRelease(url)
