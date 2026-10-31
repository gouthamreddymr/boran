from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import replace
from typing import Callable

from PIL import Image, ImageTk

from boran.models import FaceBox, face_at
from boran.title_style import TitleStyle
from boran.ui import fonts, theme
from boran.ui.title_render import EXIT_SECONDS, draw_title, duration

_NAMED = "#2ecc71"
_UNNAMED = "#e74c3c"
_SELECTED = "#f1c40f"
_VIEW_OUTLINE = "#ffffff"
_VIEW_LABEL_BG = "#202020"
_CLICK_SLOP_PX = 4
_MIN_SCALE, _MAX_SCALE = 0.02, 40.0
_MIN_NEW_FACE_PX = 8
_TITLE_LINGER_MS = 350  # keeps the title while the pointer crosses the gap between two faces
_TITLE_DOUBLE_CLICK_MS = 400
_FRAME_MS = 16

# (visible part of the image, its place in the whole photo as fractions x0 y0 x1 y1, zoom) -> edited pixels
PixelFilter = Callable[[Image.Image, tuple[float, float, float, float], float], Image.Image]

class ImageViewer(tk.Canvas):
    """Zoomable, pannable image canvas with clickable face boxes.

    Only the visible part of the image is resampled on each redraw, so cost
    depends on the window size, not the image size.
    """

    def __init__(self, master, **kw):
        super().__init__(master, background=theme.CANVAS, highlightthickness=0, **kw)
        self._img: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._fit = True
        self._faces: list[FaceBox] = []
        self._selected: int | None = None
        self._show_all = False
        self._draw_mode = False
        self._edit = True
        self._hover: int | None = None
        self._mouse: tuple[int, int] | None = None

        self._press: tuple[int, int] | None = None
        self._last: tuple[int, int] | None = None
        self._dragging = False
        self._redraw_job: str | None = None
        self._presenter = False
        self._filter: PixelFilter | None = None
        self._compare = False
        self._title_style = TitleStyle()
        self._title_text = ""
        self._title_prev = ""  # the name leaving while `_title_text` arrives
        self._title_start = 0.0
        self._title_dur = 0.0
        self._title_drag: tuple[float, float] | None = None  # pointer offset from the title's centre while dragging
        self._title_moved = False
        self._title_click = 0
        self._cursor_now = ""
        self._effect_job: str | None = None
        self._effect_start = time.monotonic()
        self.on_title_moved: Callable[[TitleStyle], None] = lambda style: None
        self._title_job: str | None = None
        self._hide_job: str | None = None

        self.on_face_click: Callable[[int | None], None] = lambda i: None
        self.on_face_menu: Callable[[int, int, int], None] = lambda i, x, y: None
        self.on_face_drawn: Callable[[int, int, int, int], None] = lambda x, y, w, h: None

        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<ButtonRelease-3>", self._on_right_click)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Motion>", self._on_hover)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Destroy>", self._on_destroy)

    # --- public API -------------------------------------------------------
    def set_image(self, image: Image.Image | None, state: tuple[float, float, float, bool] | None = None) -> None:
        """Show an image; `state` (from get_state) restores that tab's zoom and position."""
        self._img = image
        self._selected = None
        self._hover = None
        if state is not None and not state[3]:
            self._scale, self._ox, self._oy, self._fit = state
            self._clamp()
        else:
            self._fit = True
            self._apply_fit()
        self._redraw()

    def get_state(self) -> tuple[float, float, float, bool]:
        return self._scale, self._ox, self._oy, self._fit

    def set_faces(self, faces: list[FaceBox]) -> None:
        """The list is read live, not copied; call refresh() after changing it."""
        self._faces = faces
        self._selected = None
        self._hover = self._face_under(self._mouse)
        self._draw_faces()

    def refresh(self) -> None:
        self._draw_faces()

    def set_selected(self, index: int | None) -> None:
        self._selected = index if index is not None and 0 <= index < len(self._faces) else None
        self._draw_faces()

    def set_show_all(self, enabled: bool) -> None:
        self._show_all = enabled
        self._draw_faces()

    def set_edit_mode(self, enabled: bool) -> None:
        """Edit mode shows every box; view mode shows only the hovered or selected face."""
        self._edit = enabled
        self._draw_faces()

    def set_draw_mode(self, enabled: bool) -> None:
        self._draw_mode = enabled
        self._update_cursor()

    def set_filter(self, pixel_filter: PixelFilter | None) -> None:
        """Edits are shown by filtering what is on screen, so the cost follows the window, not the photo."""
        self._filter = pixel_filter
        self._request_redraw()

    def set_compare(self, enabled: bool) -> None:
        """Show the unedited photo while True."""
        if enabled != self._compare:
            self._compare = enabled
            self._request_redraw()

    def set_presenter(self, enabled: bool) -> None:
        """Presentation mode hides the image's chrome. With `labels == "title"` it also hides the face boxes and shows the
        hovered person's name as one title; with "individual" it keeps the hover box and label on each face."""
        self._presenter = enabled
        self._update_cursor()
        self._draw_faces()
        if not enabled:
            self._hide_title(immediate=True)

    @property
    def title_style(self) -> TitleStyle:
        return self._title_style

    def set_title_style(self, style: TitleStyle) -> None:
        switched = style.labels != self._title_style.labels
        self._title_style = style
        if switched:
            self._update_cursor()
            self._draw_faces()  # shows or hides the face boxes and the title for the new mode
        if self._title_text and self._title_job is None:
            self._draw_title(1.0)
            self._ensure_effect()
    def fit(self) -> None:
        self._fit = True
        self._apply_fit()
        self._redraw()

    def actual_size(self) -> None:
        self.zoom_to(1.0)

    def zoom_by(self, factor: float) -> None:
        self.zoom_to(self._scale * factor)

    def zoom_to(self, scale: float, anchor: tuple[float, float] | None = None) -> None:
        if self._img is None:
            return
        new = min(_MAX_SCALE, max(_MIN_SCALE, scale))
        ax, ay = anchor if anchor else (self.winfo_width() / 2, self.winfo_height() / 2)
        self._ox = ax - (ax - self._ox) * new / self._scale
        self._oy = ay - (ay - self._oy) * new / self._scale
        self._scale = new
        self._fit = False
        self._clamp()
        self._request_redraw()

    # --- geometry ---------------------------------------------------------
    def _apply_fit(self) -> None:
        if self._img is None:
            return
        cw, ch = max(1, self.winfo_width()), max(1, self.winfo_height())
        iw, ih = self._img.size
        self._scale = min(_MAX_SCALE, max(_MIN_SCALE, min(cw / iw, ch / ih)))
        self._ox = (cw - iw * self._scale) / 2
        self._oy = (ch - ih * self._scale) / 2

    def _clamp(self) -> None:
        if self._img is None:
            return
        cw, ch = self.winfo_width(), self.winfo_height()
        iw, ih = self._img.size[0] * self._scale, self._img.size[1] * self._scale
        self._ox = (cw - iw) / 2 if iw <= cw else min(0.0, max(cw - iw, self._ox))
        self._oy = (ch - ih) / 2 if ih <= ch else min(0.0, max(ch - ih, self._oy))

    def _to_image(self, cx: float, cy: float) -> tuple[float, float]:
        return (cx - self._ox) / self._scale, (cy - self._oy) / self._scale

    # --- drawing ----------------------------------------------------------
    def _request_redraw(self) -> None:
        """Coalesce bursts of pan/zoom/resize events into one redraw."""
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self.delete("all")
        cw, ch = self.winfo_width(), self.winfo_height()
        if self._img is None:
            self._hide_title(immediate=True)
            self.create_text(
                cw / 2, ch / 2, fill="#aaaaaa", font=(fonts.family(), 10),
                text="Drag and drop an image here\nor press Ctrl+O / click Open", justify="center",
            )
            return
        s = self._scale
        iw, ih = self._img.size
        x0, y0 = max(0.0, -self._ox / s), max(0.0, -self._oy / s)
        x1, y1 = min(float(iw), (cw - self._ox) / s), min(float(ih), (ch - self._oy) / s)
        if x1 > x0 and y1 > y0:
            box = (int(x0), int(y0), min(iw, math.ceil(x1)), min(ih, math.ceil(y1)))
            size = (max(1, round((box[2] - box[0]) * s)), max(1, round((box[3] - box[1]) * s)))
            resample = Image.Resampling.NEAREST if s >= 4 else Image.Resampling.BILINEAR
            crop = self._img.crop(box).resize(size, resample, reducing_gap=2.0 if s < 1 else None)
            if self._filter is not None and not self._compare:
                crop = self._filter(crop, (box[0] / iw, box[1] / ih, box[2] / iw, box[3] / ih), s)
            self._photo = ImageTk.PhotoImage(crop)
            self.create_image(self._ox + box[0] * s, self._oy + box[1] * s, anchor="nw", image=self._photo)
        self._hover = self._face_under(self._mouse)
        self._update_cursor()
        self._draw_faces()
        if self._title_text and self._title_job is None:
            self._draw_title(1.0)  # the redraw wiped it; a running animation redraws it itself
            self._ensure_effect()

    def _draw_faces(self) -> None:
        self.delete("overlay")
        self._sync_title()
        if self._img is None or self._universal_title():
            return
        cw, ch = self.winfo_width(), self.winfo_height()
        s = self._scale
        for i, f in enumerate(self._faces):
            hovered, selected = i == self._hover, i == self._selected
            if not (self._edit or hovered or selected):
                continue
            left, top = self._ox + f.x * s, self._oy + f.y * s
            right, bottom = left + f.w * s, top + f.h * s
            if right < 0 or bottom < 0 or left > cw or top > ch:
                continue
            if self._edit:
                color = _SELECTED if selected else (_NAMED if f.name else _UNNAMED)
                label_bg, label_fg = color, "black" if selected else "white"
            else:
                color, label_bg, label_fg = _VIEW_OUTLINE, _VIEW_LABEL_BG, "white" if f.name else "#aaaaaa"
            if not self._presenter:  # Full View shows just the name label, without the box
                self.create_rectangle(
                    left, top, right, bottom, outline=color, width=3 if selected else 2, tags="overlay"
                )
            if hovered or selected or self._show_all:
                self._draw_label(f.name or "Unnamed", left, top, bottom, ch, label_bg, label_fg)

    def _draw_label(self, text: str, left: float, top: float, bottom: float, ch: int, bg: str, fg: str) -> None:
        below = bottom + 26 <= ch
        item = self.create_text(
            left + 4, bottom + 3 if below else top - 3, anchor="nw" if below else "sw", text=text,
            fill=fg, font=(fonts.family(), 11, "bold"), tags="overlay",
        )
        x0, y0, x1, y1 = self.bbox(item)
        back = self.create_rectangle(x0 - 4, y0 - 2, x1 + 4, y1 + 2, fill=bg, outline="", tags="overlay")
        self.tag_lower(back, item)

    # --- presentation title -----------------------------------------------
    def _universal_title(self) -> bool:
        """True while the one-title-at-the-top mode is on (presentation mode only)."""
        return self._presenter and self._title_style.labels == "title"

    def _sync_title(self) -> None:
        """Show the hovered person's name, switch it when the pointer moves to someone else, hide it after a pause."""
        if not self._universal_title():
            if self._title_text or self._title_prev:
                self._hide_title(immediate=True)
            return
        face = None
        if self._hover is not None and self._hover < len(self._faces):
            face = self._faces[self._hover]
        wanted = face.name if face else ""
        held = self._title_drag is not None or self._over_title(self._mouse)  # the pointer is on the title itself
        if wanted or held:
            if self._hide_job is not None:
                self.after_cancel(self._hide_job)
                self._hide_job = None
            if wanted and wanted != self._title_text:
                self._title_prev = self._title_text  # empty while exiting, so the new name enters afresh
                self._title_text = wanted
                self._start_title(duration(self._title_style, wanted))
        elif self._title_text and self._hide_job is None:
            self._hide_job = self.after(_TITLE_LINGER_MS, self._hide_title)

    def _start_title(self, seconds: float) -> None:
        self._title_start = time.monotonic()
        self._title_dur = seconds
        if self._title_job is not None:
            self.after_cancel(self._title_job)
        self._step_title()

    def _hide_title(self, immediate: bool = False) -> None:
        if self._hide_job is not None:
            self.after_cancel(self._hide_job)
            self._hide_job = None
        if immediate or not self._title_text or (
            self._title_style.motion == "none" and self._title_style.box_motion == "none"
        ):
            if self._title_job is not None:
                self.after_cancel(self._title_job)
                self._title_job = None
            self._title_text = self._title_prev = ""
            self.delete("title")
            return
        self._title_prev, self._title_text = self._title_text, ""
        self._start_title(EXIT_SECONDS)

    def _step_title(self) -> None:
        self._title_job = None
        p = 1.0 if self._title_dur <= 0 else min(1.0, (time.monotonic() - self._title_start) / self._title_dur)
        self._draw_title(p)
        if p < 1:
            self._title_job = self.after(_FRAME_MS, self._step_title)
        else:
            self._title_prev = ""
            if not self._title_text:
                self.delete("title")
            self._ensure_effect()

    def _draw_title(self, progress: float) -> None:
        clock = time.monotonic() - self._effect_start
        draw_title(self, self._title_text, self._title_style, progress, previous=self._title_prev, clock=clock)

    def _effect_running(self) -> bool:
        return bool(
            self._title_text and not self._title_prev and self._title_job is None and self._title_drag is None
            and self._title_style.effect != "none"
        )

    def _ensure_effect(self) -> None:
        if self._effect_job is None and self._effect_running():
            self._effect_job = self.after(_FRAME_MS * 2, self._tick_effect)

    def _tick_effect(self) -> None:
        self._effect_job = None
        if self._effect_running():
            self._draw_title(1.0)
            self._ensure_effect()

    def _over_title(self, pos: tuple[int, int] | None) -> bool:
        if pos is None or not self._universal_title() or not self._title_text:
            return False
        box = self.bbox("title")
        return box is not None and box[0] <= pos[0] <= box[2] and box[1] <= pos[1] <= box[3]

    def _press_title(self, event) -> None:
        """Start dragging the title; a quick second press puts it back at its preset position."""
        if event.time - self._title_click < _TITLE_DOUBLE_CLICK_MS:
            self._title_click = 0
            self._place_title(replace(self._title_style, x=None, y=None))
            self.on_title_moved(self._title_style)
            return
        self._title_click = event.time
        x0, y0, x1, y1 = self.bbox("title")
        self._title_drag = (event.x - (x0 + x1) / 2, event.y - (y0 + y1) / 2)
        self._title_moved = False
        self._update_cursor()

    def _drag_title(self, event) -> None:
        assert self._title_drag is not None
        cw, ch = max(1, self.winfo_width()), max(1, self.winfo_height())
        x = min(1.0, max(0.0, (event.x - self._title_drag[0]) / cw))
        y = min(1.0, max(0.0, (event.y - self._title_drag[1]) / ch))
        self._title_moved = True
        self._place_title(replace(self._title_style, x=x, y=y))

    def _place_title(self, style: TitleStyle) -> None:
        self._title_style = style
        if self._title_job is not None:  # a moved title stops animating and just follows the pointer
            self.after_cancel(self._title_job)
            self._title_job = None
        self._title_prev = ""
        self._draw_title(1.0)
        self._ensure_effect()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            for job in (self._title_job, self._hide_job, self._redraw_job, self._effect_job):
                if job is not None:
                    self.after_cancel(job)

    def _face_under(self, pos: tuple[int, int] | None) -> int | None:
        if pos is None or self._img is None:
            return None
        return face_at(self._faces, *self._to_image(*pos))

    def _update_cursor(self) -> None:
        if self._title_drag is not None or self._over_title(self._mouse):
            wanted = "fleur"
        elif self._draw_mode:
            wanted = "crosshair"
        else:
            wanted = "hand2" if self._hover is not None and not self._universal_title() else ""
        if wanted != self._cursor_now:
            self._cursor_now = wanted
            self.configure(cursor=wanted)

    # --- events -----------------------------------------------------------
    def _on_hover(self, event) -> None:
        self._mouse = (event.x, event.y)
        hover = self._face_under(self._mouse)
        if hover != self._hover:
            self._hover = hover
            self._draw_faces()
        else:
            self._sync_title()
        self._update_cursor()

    def _on_leave(self, _event) -> None:
        self._mouse = None
        if self._hover is not None:
            self._hover = None
            self._draw_faces()
        else:
            self._sync_title()
        self._update_cursor()

    def _on_configure(self, _event) -> None:
        if self._fit:
            self._apply_fit()
        else:
            self._clamp()
        self._request_redraw()

    def _on_wheel(self, event) -> None:
        if self._img is None or event.delta == 0:
            return
        self._mouse = (event.x, event.y)
        self.zoom_to(self._scale * 1.15 ** (event.delta / 120), (event.x, event.y))

    def _on_press(self, event) -> None:
        if self._over_title((event.x, event.y)):
            self._press_title(event)
            return
        self._press = self._last = (event.x, event.y)
        self._dragging = False
        self.focus_set()

    def _on_motion(self, event) -> None:
        if self._title_drag is not None:
            self._mouse = (event.x, event.y)
            self._drag_title(event)
            return
        if self._press is None or self._img is None:
            return
        self._mouse = (event.x, event.y)
        if not self._dragging and abs(event.x - self._press[0]) + abs(event.y - self._press[1]) <= _CLICK_SLOP_PX:
            return
        self._dragging = True
        if self._draw_mode:
            self.delete("band")
            self.create_rectangle(*self._press, event.x, event.y, outline="white", dash=(4, 3), tags="band")
            return
        assert self._last is not None
        self._ox += event.x - self._last[0]
        self._oy += event.y - self._last[1]
        self._last = (event.x, event.y)
        self._fit = False
        self._clamp()
        self._request_redraw()

    def _on_release(self, event) -> None:
        if self._title_drag is not None:
            self._title_drag = None
            self._update_cursor()
            self._ensure_effect()
            if self._title_moved:
                self.on_title_moved(self._title_style)
            return
        press, dragged = self._press, self._dragging
        self._press, self._last, self._dragging = None, None, False
        if press is None or self._img is None:
            return
        if dragged:
            if self._draw_mode:
                self.delete("band")
                self._emit_drawn(press, (event.x, event.y))
            return
        self.on_face_click(self._face_under((event.x, event.y)))

    def _on_right_click(self, event) -> None:
        index = self._face_under((event.x, event.y))
        if index is not None:
            self.on_face_menu(index, event.x_root, event.y_root)

    def _emit_drawn(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        assert self._img is not None
        (ax, ay), (bx, by) = self._to_image(*a), self._to_image(*b)
        iw, ih = self._img.size
        left, right = max(0, min(ax, bx)), min(iw, max(ax, bx))
        top, bottom = max(0, min(ay, by)), min(ih, max(ay, by))
        w, h = int(right - left), int(bottom - top)
        if w >= _MIN_NEW_FACE_PX and h >= _MIN_NEW_FACE_PX:
            self.on_face_drawn(int(left), int(top), w, h)
