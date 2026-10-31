from __future__ import annotations

import time
import tkinter as tk
from tkinter import colorchooser
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from boran.title_style import (
    BOX_MOTIONS, EASING_LABELS, EFFECTS, LABELS, MAX_SIZE, MAX_SPEED, MIN_SIZE, MIN_SPEED, MOTIONS, POSITIONS, SHADOWS,
    SHAPES, TitleStyle, sanitize,
)
from boran.ui import theme
from boran.ui.title_render import draw_title, duration

_APP_FONT = "App font"
_SAMPLE = "Goutham Reddy"
_PREVIEW_SIZE = (460, 250)
_PREVIEW_SCALE = 0.3
_HOLD_SECONDS = 3.5  # how long the preview shows the settled title before replaying the entrance


def _label_for(options: dict[str, str], value: str) -> str:
    return next((label for label, v in options.items() if v == value), next(iter(options)))


def _backdrop() -> Image.Image:
    """A photo-like backdrop so transparency and shadows can be judged."""
    w, h = _PREVIEW_SIZE
    image = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(image)
    for y in range(h):
        draw.line([(0, y), (w, y)], fill=(54 + y // 5, 74 + y // 6, 110 + y // 4))
    for cx in (130, 235, 340):
        draw.ellipse((cx - 38, 110, cx + 38, 215), fill=(214, 172, 142))
    return image


def ask_title_style(parent: tk.Misc, current: TitleStyle) -> TitleStyle | None:
    """Modal editor for the Full View name title with a live, replaying preview. None means cancelled."""
    result: list[TitleStyle | None] = [None]

    dlg = tk.Toplevel(parent, bg=theme.BG)
    dlg.title("Presentation title")
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)

    frame = ttk.Frame(dlg, padding=14)
    frame.pack(fill="both", expand=True)

    families = [_APP_FONT] + sorted({f for f in tkfont.families(dlg) if not f.startswith("@")}, key=str.lower)
    position = tk.StringVar(value=_label_for(POSITIONS, current.position))
    font = tk.StringVar(value=current.font or _APP_FONT)
    size = tk.StringVar(value=str(current.size))
    labels = tk.StringVar(value=_label_for(LABELS, current.labels))
    text_color = tk.StringVar(value=current.text_color)
    accent = tk.StringVar(value=current.accent)
    accent_opacity = tk.StringVar(value=str(current.accent_opacity))
    accent_transparent = tk.BooleanVar(value=current.accent_opacity == 0)
    motion = tk.StringVar(value=_label_for(MOTIONS, current.motion))
    effect = tk.StringVar(value=_label_for(EFFECTS, current.effect))
    speed = tk.StringVar(value=str(current.speed))
    easing = tk.StringVar(value=_label_for(EASING_LABELS, current.easing))
    shape = tk.StringVar(value=_label_for(SHAPES, current.shape))
    bg_color = tk.StringVar(value=current.bg_color)
    opacity = tk.StringVar(value=str(current.bg_opacity))
    transparent = tk.BooleanVar(value=current.bg_opacity == 0)
    border = tk.BooleanVar(value=current.border)
    shadow = tk.StringVar(value=_label_for(SHADOWS, current.shadow))
    box_motion = tk.StringVar(value=_label_for(BOX_MOTIONS, current.box_motion))
    free = [current.x, current.y]  # a dragged position, dropped when a preset position is picked

    def number(var: tk.StringVar, fallback: int) -> int:
        try:
            return int(var.get())
        except ValueError:
            return fallback

    def read() -> TitleStyle:
        return sanitize({
            "position": POSITIONS.get(position.get()), "font": "" if font.get() == _APP_FONT else font.get(),
            "size": number(size, current.size), "labels": LABELS.get(labels.get()),
            "text_color": text_color.get(), "accent": accent.get(),
            "accent_opacity": 0 if accent_transparent.get() else number(accent_opacity, current.accent_opacity),
            "motion": MOTIONS.get(motion.get()), "effect": EFFECTS.get(effect.get()),
            "speed": number(speed, current.speed), "easing": EASING_LABELS.get(easing.get()),
            "shape": SHAPES.get(shape.get()), "bg_color": bg_color.get(),
            "bg_opacity": 0 if transparent.get() else number(opacity, current.bg_opacity),
            "shadow": SHADOWS.get(shadow.get()), "box_motion": BOX_MOTIONS.get(box_motion.get()),
            "border": border.get(),
            "x": free[0], "y": free[1],
        })

    preview = tk.Canvas(frame, width=_PREVIEW_SIZE[0], height=_PREVIEW_SIZE[1], highlightthickness=1,
                        highlightbackground=theme.BORDER)
    preview.pack(pady=(0, 10))
    backdrop = ImageTk.PhotoImage(_backdrop())
    preview.create_image(0, 0, anchor="nw", image=backdrop)

    started = [time.monotonic()]
    job: list[str | None] = [None]

    def play(*_args) -> None:
        started[0] = time.monotonic()

    def frame_tick() -> None:
        if not dlg.winfo_exists():
            return
        style = read()
        elapsed = time.monotonic() - started[0]
        span = duration(style, _SAMPLE)
        if elapsed > span + _HOLD_SECONDS:
            play()
            elapsed = 0.0
        draw_title(preview, _SAMPLE, style, 1.0 if span <= 0 else min(1.0, elapsed / span), _PREVIEW_SCALE, clock=elapsed)
        job[0] = dlg.after(33, frame_tick)

    tabs = ttk.Notebook(frame)
    tabs.pack(fill="x")

    def tab(title: str) -> ttk.Frame:
        page = ttk.Frame(tabs, padding=(12, 10))
        page.columnconfigure(1, weight=1)
        tabs.add(page, text=title)
        return page

    def row(page: ttk.Frame, index: int, text: str, widget: tk.Widget) -> None:
        ttk.Label(page, text=text, style="Dialog.TLabel").grid(row=index, column=0, sticky="w", pady=4, padx=(0, 16))
        widget.grid(row=index, column=1, sticky="w", pady=4)

    def combo(page: ttk.Frame, var: tk.StringVar, values: list[str], width: int = 24) -> ttk.Combobox:
        box = ttk.Combobox(page, textvariable=var, values=values, width=width, state="readonly", style="Dialog.TCombobox",
                           font=theme.DIALOG_FONT)
        box.bind("<<ComboboxSelected>>", play)
        return box

    def spin(page: ttk.Frame, var: tk.StringVar, low: int, high: int, step: int = 1) -> ttk.Spinbox:
        box = ttk.Spinbox(page, from_=low, to=high, increment=step, textvariable=var, width=8, font=theme.DIALOG_FONT,
                          command=play)
        box.bind("<KeyRelease>", play)
        return box

    def swatch(page: ttk.Frame, var: tk.StringVar, title: str) -> tk.Label:
        """A colour chip showing the current colour; clicking opens the colour picker."""
        chip = tk.Label(page, width=12, cursor="hand2", relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=theme.BORDER, font=theme.DIALOG_FONT)

        def paint(*_a) -> None:
            value = var.get()
            light = sum(int(value[i:i + 2], 16) for i in (1, 3, 5)) > 380
            chip.configure(bg=value, text=value, fg="#000000" if light else "#ffffff")

        def pick(_event=None) -> None:
            chosen = colorchooser.askcolor(color=var.get(), parent=dlg, title=title)[1]
            if chosen:
                var.set(chosen.lower())
                play()

        var.trace_add("write", paint)
        chip.bind("<Button-1>", pick)
        paint()
        return chip

    def untransparent(flag: tk.BooleanVar, level: tk.StringVar) -> None:
        """Unticking Transparent while the opacity is 0 would change nothing, so restore full opacity."""
        if not flag.get() and number(level, 0) == 0:
            level.set("100")
        play()

    # --- Layout ---
    layout_page = tab("Layout")

    def pick_position(_event=None) -> None:
        free[:] = [None, None]
        play()

    position_box = combo(layout_page, position, list(POSITIONS))
    position_box.bind("<<ComboboxSelected>>", pick_position)
    row(layout_page, 0, "Position", position_box)
    row(layout_page, 1, "Font", combo(layout_page, font, families))
    row(layout_page, 2, "Size", spin(layout_page, size, MIN_SIZE, MAX_SIZE))
    row(layout_page, 3, "Full View shows", combo(layout_page, labels, list(LABELS)))

    # --- Text ---
    text_page = tab("Text")
    row(text_page, 0, "Text colour", swatch(text_page, text_color, "Text colour"))
    row(text_page, 1, "Accent colour", swatch(text_page, accent, "Accent colour (glow, pulse, gradient)"))
    row(text_page, 2, "Accent opacity %", spin(text_page, accent_opacity, 0, 100, 5))
    row(
        text_page, 3, "",
        ttk.Checkbutton(
            text_page, text="Transparent accent", variable=accent_transparent,
            command=lambda: untransparent(accent_transparent, accent_opacity),
        ),
    )
    row(text_page, 4, "Transition", combo(text_page, motion, list(MOTIONS)))
    row(text_page, 5, "Easing", combo(text_page, easing, list(EASING_LABELS)))
    row(text_page, 6, "Effect", combo(text_page, effect, list(EFFECTS)))
    row(text_page, 7, "Effect speed %", spin(text_page, speed, MIN_SPEED, MAX_SPEED, 25))

    # --- Box ---
    box_page = tab("Box")
    row(box_page, 0, "Style", combo(box_page, shape, list(SHAPES)))
    row(box_page, 1, "Background colour", swatch(box_page, bg_color, "Background colour"))
    row(box_page, 2, "Opacity %", spin(box_page, opacity, 0, 100, 5))
    check = ttk.Checkbutton(
        box_page, text="Transparent background", variable=transparent,
        command=lambda: untransparent(transparent, opacity),
    )
    row(box_page, 3, "", check)
    row(box_page, 4, "Shadow", combo(box_page, shadow, list(SHADOWS)))
    row(box_page, 5, "Box transition", combo(box_page, box_motion, list(BOX_MOTIONS)))
    row(box_page, 6, "", ttk.Checkbutton(box_page, text="Show border", variable=border, command=play))

    def accept(_event=None) -> None:
        result[0] = read()
        dlg.destroy()

    def reset() -> None:
        default = TitleStyle()
        free[:] = [None, None]
        for var, options, value in (
            (position, POSITIONS, default.position), (labels, LABELS, default.labels), (motion, MOTIONS, default.motion),
            (effect, EFFECTS, default.effect), (easing, EASING_LABELS, default.easing), (shape, SHAPES, default.shape),
            (shadow, SHADOWS, default.shadow), (box_motion, BOX_MOTIONS, default.box_motion),
        ):
            var.set(_label_for(options, value))
        font.set(_APP_FONT)
        size.set(str(default.size))
        speed.set(str(default.speed))
        opacity.set(str(default.bg_opacity))
        transparent.set(False)
        border.set(default.border)
        text_color.set(default.text_color)
        accent.set(default.accent)
        accent_opacity.set(str(default.accent_opacity))
        accent_transparent.set(False)
        bg_color.set(default.bg_color)
        play()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(14, 0))
    ttk.Button(buttons, text="Reset", command=reset, style="Dialog.TButton").pack(side="left")
    ttk.Button(buttons, text="Replay", command=play, style="Dialog.TButton").pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Cancel", command=dlg.destroy, style="Dialog.TButton").pack(side="right")
    ttk.Button(buttons, text="OK", command=accept, style="Dialog.TButton").pack(side="right", padx=(0, 6))

    dlg.bind("<Return>", accept)
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.bind("<Destroy>", lambda e: job[0] is not None and e.widget is dlg and dlg.after_cancel(job[0]))

    dlg.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - dlg.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    theme.dark_titlebar(dlg)
    dlg.update()
    if not dlg.winfo_exists():  # closed while it was still opening
        return result[0]
    frame_tick()

    dlg.grab_set()
    dlg.wait_window()
    return result[0]
