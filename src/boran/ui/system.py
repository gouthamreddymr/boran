from __future__ import annotations

import re
import sys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

MOD = "Command" if IS_MAC else "Control"  # Tk modifier behind the Ctrl+<letter> shortcuts
RIGHT_BUTTON = 2 if IS_MAC else 3  # Tk numbers the secondary and middle buttons the other way round on macOS
MIDDLE_BUTTON = 3 if IS_MAC else 2

_CTRL = re.compile(r"Ctrl\+(?!(?:Shift\+)?Tab)")  # Ctrl+Tab stays Control on macOS, as in every Mac app


def keys(text: str) -> str:
    """Write a shortcut the way this platform names it: Ctrl+O becomes Cmd+O on macOS."""
    return _CTRL.sub("Cmd+", text) if IS_MAC else text


def wheel_notches(event) -> float:
    """Mouse-wheel movement in notches: Windows reports 120 per notch, macOS reports small per-event steps."""
    return event.delta / 3 if IS_MAC else event.delta / 120
