from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from boran.edits import Edits
from boran.models import FaceBox


@dataclass(eq=False)
class Document:
    """One open image (one tab) with its faces and view state."""

    uid: int
    path: Path
    image: Image.Image
    faces: list[FaceBox]
    image_name: str
    image_bytes: bytes | None = None  # original encoded bytes; read lazily when saving
    brn_path: Path | None = None  # where Save writes
    dirty: bool = False
    edits: Edits = field(default_factory=Edits)  # non-destructive; `image` and the saved bytes stay the original
    edit: bool = True
    selected: int | None = None
    view: tuple[float, float, float, bool] | None = None
    det_token: int = 0
    detecting: bool = False
    progress: tuple[int, float, str] | None = None  # token, fraction, status text
    detect_error: str | None = None
    closed: bool = False
