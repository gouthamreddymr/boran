from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes

from boran.ui import theme

_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_SYSMENU = 0x00080000
_SWP_FRAME_ONLY = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # no size, move, z-order or activation change; apply frame
_WM_NCLBUTTONDOWN = 0x00A1
_HTCAPTION = 2
_DWMWA_DARK_MODE = (20, 19)  # 19 on older Windows 10 builds
_DWMWA_BORDER_COLOR = 34  # Windows 11
_DWMWA_CAPTION_COLOR = 35  # Windows 11


def _colorref(hex_color: str) -> int:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return (b << 16) | (g << 8) | r


def _paint_frame(hwnd: int) -> None:
    """Colour the sizing frame that Windows still draws around the window so it matches the app."""
    dwm = ctypes.windll.dwmapi
    dark = ctypes.c_int(1)
    for attribute in _DWMWA_DARK_MODE:
        if dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(dark), 4) == 0:
            break
    for attribute, color in ((_DWMWA_CAPTION_COLOR, theme.BG), (_DWMWA_BORDER_COLOR, theme.BORDER)):
        value = ctypes.c_uint(_colorref(color))
        dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4)  # ignored where unsupported


def available() -> bool:
    return sys.platform == "win32"


_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def round_corners(window: tk.Misc) -> None:
    """Ask Windows 11 to round a borderless window's corners (ignored elsewhere)."""
    if not available():
        return
    try:
        user32 = ctypes.windll.user32
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(_DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), 4
        )
    except (AttributeError, OSError):
        pass


def _hwnd(window: tk.Misc) -> int:
    user32 = ctypes.windll.user32
    user32.GetParent.restype = wintypes.HWND
    return user32.GetParent(window.winfo_id())


def has_caption(window: tk.Misc) -> bool:
    if not available():
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        return (user32.GetWindowLongPtrW(_hwnd(window), _GWL_STYLE) & _WS_CAPTION) == _WS_CAPTION
    except (AttributeError, OSError):
        return False


def strip_caption(window: tk.Misc) -> None:
    """Remove the native title bar but keep resizing, minimise and the taskbar entry."""
    if not available():
        return
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        window.update_idletasks()
        hwnd = _hwnd(window)
        style = user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        style = (style & ~_WS_CAPTION) | _WS_THICKFRAME | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX | _WS_SYSMENU
        user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, style)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, _SWP_FRAME_ONLY)
        _paint_frame(hwnd)
    except (AttributeError, OSError):
        pass


def start_move(window: tk.Misc) -> None:
    """Hand the mouse to Windows so it drags (and snaps) the window as if by its title bar."""
    if not available():
        return
    try:
        user32 = ctypes.windll.user32
        user32.ReleaseCapture()
        user32.SendMessageW(_hwnd(window), _WM_NCLBUTTONDOWN, _HTCAPTION, 0)
    except (AttributeError, OSError):
        pass
