"""Context-aware tips for the status bar: only shortcuts that fit what the user is doing right now."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Context:
    """A snapshot of what the user is doing; kept small so equal snapshots mean 'nothing changed'."""

    has_doc: bool = False
    editing: bool = False
    adding: bool = False
    full: bool = False
    dirty: bool = False
    detecting: bool = False
    faces: int = 0
    unnamed: int = 0
    tabs: int = 0
    fitted: bool = True
    tree_visible: bool = False
    siblings: bool = False  # other images in the same folder


@dataclass(frozen=True)
class Tip:
    keys: str
    text: str
    when: Callable[[Context], bool]
    priority: int = 0


def _tip(keys: str, text: str, priority: int, when: Callable[[Context], bool]) -> Tip:
    return Tip(keys, text, when, priority)


def _editing(c: Context) -> bool:
    return c.has_doc and c.editing and not c.adding


TIPS: tuple[Tip, ...] = (
    # nothing open
    _tip("Ctrl+O", "Open one or more photos", 3, lambda c: not c.has_doc),
    _tip("Drop", "Drag photos onto the window to open them as tabs", 2, lambda c: not c.has_doc),
    _tip("Ctrl+Shift+O", "Open a folder and browse it in the side panel", 2, lambda c: not c.has_doc),
    _tip("Ctrl+B", "Show or hide the folder panel", 1, lambda c: not c.has_doc and not c.tree_visible),
    # detection running
    _tip("", "Faces are being detected in the background - you can keep working", 5, lambda c: c.has_doc and c.detecting),
    _tip("Ctrl+D", "Add a face by hand while detection runs", 3, lambda c: _editing(c) and c.detecting),
    # adding faces
    _tip("Drag", "Draw a box around a face to add it", 8, lambda c: c.has_doc and c.adding),
    _tip("Click", "Click an existing box to rename it", 4, lambda c: c.has_doc and c.adding),
    _tip("Ctrl+D", "Turn Add face off when you are done", 3, lambda c: c.has_doc and c.adding),
    # naming faces
    _tip("Click", "Click a face to name it", 6, lambda c: _editing(c) and c.unnamed > 0),
    _tip("Right-click", "Rename, clear or delete a face", 4, lambda c: _editing(c) and c.faces > 0),
    _tip("Ctrl+D", "No faces found? Draw one by hand", 7, lambda c: _editing(c) and c.faces == 0 and not c.detecting),
    _tip("Ctrl+R", "Run face detection again", 4, lambda c: _editing(c) and c.faces == 0 and not c.detecting),
    _tip("Ctrl+D", "Add a face the detector missed", 3, lambda c: _editing(c) and c.faces > 0 and not c.detecting),
    _tip("Ctrl+E", "All named - switch to hover view to check", 5, lambda c: _editing(c) and c.faces > 0 and c.unnamed == 0),
    # unsaved work
    _tip("Ctrl+S", "Save your names to a .brn file", 7, lambda c: c.has_doc and c.dirty),
    _tip("Ctrl+Shift+S", "Save a copy under a new name", 2, lambda c: c.has_doc and c.dirty),
    # hover view
    _tip("Hover", "Hover a face to see who it is", 6, lambda c: c.has_doc and not c.editing and c.faces > 0 and not c.full),
    _tip("F11", "Full View: just the image, with hover names", 4, lambda c: c.has_doc and not c.editing and not c.full),
    _tip("Ctrl+E", "Edit mode lets you rename or add faces", 3, lambda c: c.has_doc and not c.editing and not c.full),
    # full view
    _tip("Esc", "Leave Full View", 9, lambda c: c.full),
    _tip("Hover", "Hover a face to see its name", 5, lambda c: c.full and c.faces > 0),
    _tip("T", "Switch between one title at the top and a label on each face", 4, lambda c: c.full and c.faces > 0),
    # browsing, tabs and zoom
    _tip("Left / Right", "Previous or next photo in this folder", 2, lambda c: c.has_doc and c.siblings),
    _tip("Ctrl+B", "Browse this folder in the side panel", 2, lambda c: c.has_doc and c.siblings and not c.tree_visible),
    _tip("Ctrl+Tab", "Switch to the next tab", 2, lambda c: c.tabs > 1),
    _tip("Ctrl+W", "Close this tab", 1, lambda c: c.tabs > 1),
    _tip("0", "Fit the whole image in the window", 4, lambda c: c.has_doc and not c.fitted),
    _tip("Wheel", "Scroll to zoom, drag to pan", 2, lambda c: c.has_doc and c.fitted and not c.full),
    _tip("1", "Show the image at 100%", 1, lambda c: c.has_doc and c.fitted and not c.full),
)


def relevant(ctx: Context) -> list[Tip]:
    """Tips that fit `ctx`, most useful first."""
    return sorted((t for t in TIPS if t.when(ctx)), key=lambda t: -t.priority)


class Rotator:
    """Cycles through the tips for the current context; a context change jumps to the most useful one."""

    def __init__(self) -> None:
        self._ctx: Context | None = None
        self._tips: list[Tip] = []
        self._index = 0

    def update(self, ctx: Context) -> Tip | None:
        """Returns the tip to show right now if the context changed, else None."""
        if ctx == self._ctx:
            return None
        self._ctx = ctx
        self._tips = relevant(ctx)
        self._index = 0
        return self._tips[0] if self._tips else None

    def next(self) -> Tip | None:
        if not self._tips:
            return None
        self._index = (self._index + 1) % len(self._tips)
        return self._tips[self._index]
