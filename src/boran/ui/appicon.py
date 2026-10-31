from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

from PIL import Image

from boran.ui import system

_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)]


def install(root: tk.Tk) -> None:
    """Give the window, the taskbar button and every dialog a fully transparent icon, so no icon shows anywhere.

    Without this Windows draws Tk's default feather in every title bar. A real .ico keeps the transparency;
    an icon made from a Tk image would show as a black square.
    """
    if not system.IS_WIN:  # macOS shows the app bundle's icon; .ico is a Windows format
        return
    path = Path(tempfile.gettempdir()) / f"boran_blank_{os.getpid()}.ico"
    try:
        Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(path, format="ICO", sizes=_SIZES)
        root.iconbitmap(default=str(path))
    except (OSError, tk.TclError):
        return  # the default icon stays; nothing else depends on this
    finally:
        try:
            path.unlink()  # Tk has already handed the icon to Windows
        except OSError:
            pass
