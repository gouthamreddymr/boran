from __future__ import annotations

import itertools
import os
import queue
import sys
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from boran import formats, tips
from boran.brn import SUFFIX, BrnError, BrnFile, read_brn, write_brn
from boran.document import Document
from boran.edits import Edits, apply as apply_edits
from boran.models import FaceBox, iou
from boran.title_style import load_title_style, save_title_style
from boran.ui import appicon, fonts, frameless, system, theme
from boran.ui.about_dialog import show_about
from boran.ui.chip import Chip
from boran.ui.dock import RightDock
from boran.ui.edit_panels import AdjustPanel, LooksPanel
from boran.ui.filetree import FileTree
from boran.ui.darkmenu import DarkMenu
from boran.ui.menubar import MenuBar, popup
from boran.ui.name_dialog import ask_name
from boran.ui.ribbon import Ribbon, RibbonButton
from boran.ui.snackbar import SnackbarHost
from boran.ui.tabbar import TabBar
from boran.ui.title_dialog import ask_title_style
from boran.ui.viewer import ImageViewer

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _TkBase = TkinterDnD.Tk
except ImportError:  # drag and drop is optional
    DND_FILES = None
    _TkBase = tk.Tk

_DUPLICATE_IOU = 0.3
_TIP_INTERVAL_MS = 5000
_FOOTER_PAD_LEFT = 35  # px of space at the ends of the footer
_FOOTER_PAD_RIGHT = 12
_MAX_OPEN_AT_ONCE = 20
_SHORTCUTS = """File
  Ctrl+O  Open images        Ctrl+Shift+O  Open folder
  Ctrl+S  Save               Ctrl+Shift+S  Save As
  Ctrl+W  Close tab

Faces
  Ctrl+E  Edit mode          Ctrl+D  Add face
  Ctrl+R  Re-detect          Click a face in Edit mode to name it

View
  0  Fit    1  100%    +/-  Zoom    F11  Full View
  T  Full View: one title at the top / a label on each face
  Ctrl+B  Folder panel
  Ctrl+J  Edit panel: adjustments and filters
  Ctrl+Tab / Ctrl+Shift+Tab  Next / previous tab
  Left / Right  Previous / next image in the folder"""


def _open_extensions() -> frozenset[str]:
    return formats.supported_extensions() | {SUFFIX}


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


class App(_TkBase):
    def __init__(self, initial: Path | None = None):
        super().__init__()
        if system.IS_MAC:
            self.tk.call("tk", "scaling", 96 / 72)  # Tk on macOS sizes points at 72 dpi; match the Windows look
        fonts.install(self)
        theme.apply(self)
        appicon.install(self)
        self.title("Boran")
        self.geometry("1200x780")
        self.minsize(720, 460)

        self._docs: list[Document] = []
        self._doc: Document | None = None
        self._uids = itertools.count(1)
        self._known_names: set[str] = set()
        self._warned_detect = False
        self._sib_cache: tuple[Path, list[Path]] | None = None
        self._gated: list[tuple[DarkMenu, int, str]] = []
        self._tips = tips.Rotator()
        self._tip_job: str | None = None

        self._results: queue.Queue = queue.Queue()
        self._polling = False
        self._full = False

        self._add_mode = tk.BooleanVar(value=False)
        self._edit = tk.BooleanVar(value=False)
        self._show_all = tk.BooleanVar(value=False)
        self._tree_var = tk.BooleanVar(value=False)
        self._dock_var = tk.BooleanVar(value=False)
        self._title_mode = tk.BooleanVar(value=load_title_style().labels == "title")  # Full View: one title
        self._info = tk.StringVar()
        self._status = tk.StringVar()
        self._title_var = tk.StringVar(value="Boran")
        self._last_title_click = 0

        self._build_ui()
        self._update_state()
        frameless.strip_caption(self)
        self._enable_drop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if system.IS_MAC:
            self.createcommand("::tk::mac::Quit", self._on_close)  # Cmd+Q and the app menu's Quit
        threading.Thread(target=self._prewarm_detector, daemon=True).start()
        if initial is not None:
            self.after_idle(lambda: self.open_path(initial))

    @property
    def _faces(self) -> list[FaceBox]:
        return self._doc.faces if self._doc is not None else []

    # --- layout -----------------------------------------------------------
    def _build_ui(self) -> None:
        top = tk.Frame(self, bg=theme.BG)
        top.pack(side="top", fill="x")
        self._top = top
        menubar = MenuBar(top)
        menubar.pack(side="top", fill="x")
        self._menubar = menubar
        if frameless.available():  # elsewhere the native title bar already has these
            menubar.add_window_controls(self.iconify, self._toggle_maximize, self._on_close)
        info = tk.Label(menubar, textvariable=self._info, font=theme.TOOLBAR_FONT_BOLD, fg=theme.FG, bg=theme.BG)
        info.pack(side="right", padx=12)
        self._build_menus(menubar)
        title = tk.Label(menubar, textvariable=self._title_var, font=theme.TOOLBAR_FONT, fg=theme.MUTED, bg=theme.BG)
        title.pack(side="left", fill="both", expand=True)
        if frameless.available():
            for handle in (menubar, title, info):
                handle.bind("<ButtonPress-1>", self._on_title_press)
        self.bind("<Configure>", self._on_configure, add="+")
        ribbon = Ribbon(top, compact=True)
        ribbon.pack(side="top", fill="x")
        self._build_ribbon(ribbon)
        tk.Frame(top, height=1, bg=theme.BORDER).pack(side="top", fill="x")

        bar = tk.Frame(self, bg=theme.PANEL)
        bar.pack(side="bottom", fill="x")
        self._status_bar = bar
        footer_font = (fonts.family(), 9)
        self._tip_text = ttk.Label(bar, style="Status.TLabel", font=footer_font)
        self._tip_text.pack(side="right", padx=(0, _FOOTER_PAD_RIGHT))
        self._tip_keys = Chip(bar, (theme.SYSTEM_FONT, 8), fill=theme.BUTTON, fg=theme.FG, bg=theme.PANEL, radius=5)
        self._status_label = ttk.Label(
            bar, textvariable=self._status, anchor="w", style="Status.TLabel", font=footer_font
        )
        self._status_label.pack(side="left", fill="x", expand=True, padx=(_FOOTER_PAD_LEFT, 8))

        body = tk.Frame(self, bg=theme.BG)
        body.pack(side="top", fill="both", expand=True)
        self._body = body
        self._rail = tk.Frame(body, bg=theme.PANEL, width=40)
        self._rail.pack(side="left", fill="y")
        self._rail.pack_propagate(False)
        self._rail_sep = tk.Frame(body, width=1, bg=theme.BORDER)
        self._rail_sep.pack(side="left", fill="y")
        RibbonButton(
            self._rail, "Folders", self._apply_tree, "\uE8B7", var=self._tree_var, compact=True,
            tip="Folder panel (Ctrl+B)", tip_side="right",
        ).pack(pady=(6, 2))
        tk.Frame(self._rail, height=1, bg=theme.BORDER).pack(fill="x", padx=8, pady=6)
        self._btn_edit = RibbonButton(
            self._rail, "Edit", self._toggle_edit, "\uE70F", var=self._edit, compact=True,
            tip="Edit mode: name, add and delete faces (Ctrl+E)", tip_side="right",
        )
        self._btn_edit.pack(pady=2)
        self._btn_add = RibbonButton(
            self._rail, "Add", self._toggle_add, "\uE710", var=self._add_mode, compact=True,
            tip="Add face: drag on the image (Ctrl+D)", tip_side="right",
        )
        self._btn_add.pack(pady=2)

        self._paned = tk.PanedWindow(body, orient="horizontal", sashwidth=5, bg=theme.BORDER, bd=0, sashrelief="flat")
        self._paned.pack(side="left", fill="both", expand=True)
        self._dock = RightDock(body)
        self._dock.pack(side="right", fill="y", before=self._paned)
        self._dock.on_change = self._on_dock_change
        adjust_body = self._dock.add_section("adjust", "\uE9E9", "Adjust", "Adjust light, colour and detail (Ctrl+J)")
        looks_body = self._dock.add_section("looks", "\uE790", "Filters", "Filters and looks")
        self._adjust = AdjustPanel(adjust_body, self._update_edits, self._view_compare, self._reset_edits)
        self._looks = LooksPanel(looks_body, self._update_edits)
        self._tree = FileTree(self._paned, on_open=self.open_path)
        self._right = tk.Frame(self._paned, bg=theme.BG)
        self._paned.add(self._right, minsize=320, stretch="always")

        self._tabs = TabBar(self._right)
        self._tabs.pack(side="top", fill="x")
        self._tabs.on_select = self._on_tab_select
        self._tabs.on_close = self._on_tab_close
        self._view = ImageViewer(self._right)
        self._view.set_title_style(load_title_style())
        self._view.on_title_moved = self._save_title_style
        self._view.pack(fill="both", expand=True)
        self._view.on_face_click = self._on_face_click
        self._view.on_face_menu = self._show_menu
        self._view.on_face_drawn = self._add_face
        self._snacks = SnackbarHost(self._right)

        panel = tk.Frame(self._view, bg="#202020", padx=18, pady=12)
        tk.Label(
            # ( Boran Neural Engine ) Processing Facial Features
            panel, text="Boran Neural Engine is processing facial features",
            bg="#202020", fg="white", font=(fonts.family(), 11, "bold"),
        ).pack(anchor="w")
        self._progress_bar = ttk.Progressbar(panel, length=480, maximum=100)
        self._progress_bar.pack(fill="x", pady=(8, 4))
        self._progress_detail = tk.Label(panel, bg="#202020", fg="#bbbbbb", font=(fonts.family(), 9), anchor="w")
        self._progress_detail.pack(fill="x")
        self._progress_panel = panel

        mod = system.MOD
        binds = {
            f"<{mod}-o>": self._open_dialog,
            f"<{mod}-Shift-O>": self._open_folder,
            f"<{mod}-s>": self._save,
            f"<{mod}-Shift-S>": lambda: self._save(save_as=True),
            f"<{mod}-w>": self._close_active,
            f"<{mod}-d>": lambda: self._flip(self._add_mode, self._toggle_add),
            f"<{mod}-e>": lambda: self._flip(self._edit, self._toggle_edit),
            f"<{mod}-r>": self._redetect,
            f"<{mod}-b>": lambda: self._flip(self._tree_var, self._apply_tree),
            f"<{mod}-j>": lambda: self._flip(self._dock_var, self._apply_dock),
            "t": lambda: self._flip(self._title_mode, self._apply_title_mode),
            "<Control-Tab>": lambda: self._cycle_tab(1),
            "<Control-Shift-Tab>": lambda: self._cycle_tab(-1),
            "<Left>": lambda: self._arrow(-1),
            "<Right>": lambda: self._arrow(1),
            "0": self._view.fit,
            "1": self._view.actual_size,
            "+": lambda: self._view.zoom_by(1.25),
            "=": lambda: self._view.zoom_by(1.25),
            "-": lambda: self._view.zoom_by(1 / 1.25),
            "<Escape>": self._on_escape,
            "<F11>": lambda: self._set_full(not self._full),
        }
        for sequence, action in binds.items():
            self.bind(sequence, lambda _e, a=action: a())

        self._doc_buttons = (
            self._btn_save, self._btn_save_as, self._btn_edit, self._btn_fit, self._btn_100, self._btn_out, self._btn_in,
        )
        self._edit_buttons = (self._btn_add, self._btn_names, self._btn_detect)

    def _add(self, menu: DarkMenu, kind: str, gate: str | None = None, **options) -> None:
        if "accelerator" in options:
            options["accelerator"] = system.keys(options["accelerator"])
        getattr(menu, f"add_{kind}")(**options)
        if gate:
            self._gated.append((menu, menu.index("end"), gate))

    def _build_menus(self, bar: MenuBar) -> None:
        add = self._add
        file = bar.add_menu("File")
        add(file, "command", label="Open...", accelerator="Ctrl+O", command=self._open_dialog)
        add(file, "command", label="Open Folder...", accelerator="Ctrl+Shift+O", command=self._open_folder)
        file.add_separator()
        add(file, "command", "doc", label="Save", accelerator="Ctrl+S", command=self._save)
        add(file, "command", "doc", label="Save As...", accelerator="Ctrl+Shift+S", command=lambda: self._save(save_as=True))
        file.add_separator()
        add(file, "command", "doc", label="Close Tab", accelerator="Ctrl+W", command=self._close_active)
        add(file, "command", label="Exit", command=self._on_close)

        faces = bar.add_menu("Faces")
        add(faces, "checkbutton", "doc", label="Edit mode", accelerator="Ctrl+E", variable=self._edit, command=self._toggle_edit)
        add(faces, "checkbutton", "edit", label="Add face", accelerator="Ctrl+D", variable=self._add_mode, command=self._toggle_add)
        add(faces, "checkbutton", "edit", label="Show all names", variable=self._show_all, command=self._toggle_names)
        faces.add_separator()
        add(faces, "command", "edit", label="Re-detect faces", accelerator="Ctrl+R", command=self._redetect)

        view = bar.add_menu("View")
        add(view, "command", "doc", label="Fit to window", accelerator="0", command=lambda: self._view.fit())
        add(view, "command", "doc", label="Actual size (100%)", accelerator="1", command=lambda: self._view.actual_size())
        add(view, "command", "doc", label="Zoom in", accelerator="+", command=lambda: self._view.zoom_by(1.25))
        add(view, "command", "doc", label="Zoom out", accelerator="-", command=lambda: self._view.zoom_by(1 / 1.25))
        view.add_separator()
        add(view, "command", "view", label="Full View", accelerator="F11", command=lambda: self._set_full(True))
        add(
            view, "checkbutton", label="One title in Full View", accelerator="T", variable=self._title_mode,
            command=self._apply_title_mode,
        )
        add(view, "checkbutton", label="Folder panel", accelerator="Ctrl+B", variable=self._tree_var, command=self._apply_tree)
        add(view, "checkbutton", label="Edit panel", accelerator="Ctrl+J", variable=self._dock_var, command=self._apply_dock)
        add(view, "command", label="Presentation title...", command=self._edit_title_style)
        view.add_separator()
        add(view, "command", "doc", label="Previous image", accelerator="Left", command=lambda: self._step(-1))
        add(view, "command", "doc", label="Next image", accelerator="Right", command=lambda: self._step(1))
        add(view, "command", "doc", label="Next tab", accelerator="Ctrl+Tab", command=lambda: self._cycle_tab(1))
        add(view, "command", "doc", label="Previous tab", accelerator="Ctrl+Shift+Tab", command=lambda: self._cycle_tab(-1))

        helpm = bar.add_menu("Help")
        add(helpm, "command", label="Keyboard shortcuts...", command=lambda: messagebox.showinfo("Keyboard shortcuts", system.keys(_SHORTCUTS), parent=self))
        add(helpm, "command", label="About Boran", command=lambda: show_about(self))

    def _build_ribbon(self, ribbon: Ribbon) -> None:
        g = ribbon.group("File")
        g.button("Open", self._open_dialog, "\uE838", tip="Open images (Ctrl+O)")
        self._btn_save = g.button("Save", self._save, "\uE74E", tip="Save to a .brn file (Ctrl+S)")
        self._btn_save_as = g.button("Save As", lambda: self._save(save_as=True), "\uE792", tip="Save a copy (Ctrl+Shift+S)")

        g = ribbon.group("Faces")
        self._btn_names = g.button("Show names", self._toggle_names, "\uE8EC", var=self._show_all, tip="Label every face")
        self._btn_detect = g.button("Re-detect", self._redetect, "\uE72C", tip="Run face detection again (Ctrl+R)")

        g = ribbon.group("View")
        self._btn_fit = g.button("Fit", lambda: self._view.fit(), "\uE73F", tip="Fit to window (0)")
        self._btn_100 = g.button("100%", lambda: self._view.actual_size(), "1:1", text_icon=True, tip="Actual size (1)")
        self._btn_out = g.button("Zoom out", lambda: self._view.zoom_by(1 / 1.25), "\uE71F", tip="Zoom out (-)")
        self._btn_in = g.button("Zoom in", lambda: self._view.zoom_by(1.25), "\uE8A3", tip="Zoom in (+)")
        self._btn_full = g.button("Full View", lambda: self._set_full(True), "\uE740", tip="Image only, full screen (F11)")
        g.button(
            "Title", self._apply_title_mode, "\uE8D2", var=self._title_mode,
            tip="Full View names: on = one title at the top, off = a label on each face (T)",
        )

    # --- window chrome ----------------------------------------------------
    def _set_title(self, text: str) -> None:
        self.title(text)
        self._title_var.set(text)

    def _on_title_press(self, event) -> None:
        """Drag the window by the menu bar; a quick second click maximises or restores it."""
        if event.time - self._last_title_click < 400:
            self._last_title_click = 0
            self._toggle_maximize()
            return
        self._last_title_click = event.time
        if self.state() != "zoomed" and not self._full:
            frameless.start_move(self)

    def _toggle_maximize(self) -> None:
        if not self._full:
            self.state("normal" if self.state() == "zoomed" else "zoomed")

    def _on_configure(self, event) -> None:
        if event.widget is self:
            if frameless.has_caption(self):  # Tk rebuilds the window frame when leaving full screen
                frameless.strip_caption(self)
            self._menubar.set_maximized(self.state() == "zoomed")

    @staticmethod
    def _flip(var: tk.BooleanVar, command) -> None:
        var.set(not var.get())
        command()

    # --- modes ------------------------------------------------------------
    def _apply_mode(self) -> None:
        doc = self._doc
        editing = doc is not None and doc.edit
        self._edit.set(editing)
        if editing:
            self._set_full(False)
        else:
            self._add_mode.set(False)
        self._view.set_edit_mode(editing)
        self._view.set_draw_mode(self._add_mode.get() and editing)

    def _toggle_edit(self) -> None:
        if self._doc is not None:
            self._doc.edit = self._edit.get()
            self._notify("Edit mode on: click a face to name it" if self._doc.edit else "Edit mode off: hover a face to see its name")
        self._apply_mode()
        self._update_state()

    def _toggle_add(self) -> None:
        if not self._editing():
            self._add_mode.set(False)
        elif self._add_mode.get():
            self._notify("Add face on: drag on the image to draw a box")
        else:
            self._notify("Add face off")
        self._view.set_draw_mode(self._add_mode.get() and self._edit.get() and self._doc is not None)

    def _toggle_names(self) -> None:
        self._view.set_show_all(self._show_all.get())

    def _set_full(self, enable: bool) -> None:
        """Full View: only the image, full screen, with hover names. View mode only."""
        doc = self._doc
        if enable == self._full or (enable and (doc is None or doc.edit)):
            return
        self._full = enable
        chrome = (self._top, self._status_bar, self._rail, self._rail_sep, self._tabs, self._dock)
        if enable:
            for widget in chrome:
                widget.pack_forget()
            self._apply_tree()
            self.attributes("-fullscreen", True)
            self._view.set_presenter(True)
            hint = tk.Label(
                self._view, text="Esc or F11 to exit full view   |   T switches between one title and labels on faces",
                bg="#202020", fg="white", padx=10, pady=4,
            )
            hint.place(relx=0.5, rely=1.0, y=-16, anchor="s")
            self.after(4000, hint.destroy)
        else:
            self.attributes("-fullscreen", False)
            self._view.set_presenter(False)
            self._top.pack(side="top", fill="x", before=self._body)
            self._status_bar.pack(side="bottom", fill="x", before=self._body)
            self._rail.pack(side="left", fill="y", before=self._paned)
            self._rail_sep.pack(side="left", fill="y", before=self._paned)
            self._dock.pack(side="right", fill="y", before=self._paned)
            self._tabs.pack(side="top", fill="x", before=self._view)
            self._apply_tree()
            self.after_idle(lambda: frameless.strip_caption(self))  # Tk rebuilds the window frame after fullscreen

    def _edit_title_style(self) -> None:
        style = ask_title_style(self, self._view.title_style)
        if style is None:
            return
        self._view.set_title_style(style)
        self._title_mode.set(style.labels == "title")
        self._save_title_style(style)

    def _apply_title_mode(self) -> None:
        """Full View names: one title at the top, or a box and label on each face."""
        universal = self._title_mode.get()
        style = replace(self._view.title_style, labels="title" if universal else "individual")
        self._view.set_title_style(style)
        self._save_title_style(style)
        self._notify("Full View: one title at the top" if universal else "Full View: a label on each face")

    def _save_title_style(self, style) -> None:
        if not save_title_style(style):
            self._notify("Title style applied, but it could not be saved", "warning")

    def _on_escape(self) -> None:
        if self._full:
            self._set_full(False)
        else:
            self._on_face_click(None)

    # --- state ------------------------------------------------------------
    @staticmethod
    def _style_entry(menu: DarkMenu, index: int, available: bool) -> None:
        """Dim an unavailable item: it stays clickable (its command ignores the click) but is greyed and not highlighted."""
        if available:
            menu.entryconfigure(index, foreground=theme.FG, activeforeground="white", activebackground=theme.MENU_ACTIVE)
        else:
            menu.entryconfigure(
                index, foreground=theme.DISABLED, activeforeground=theme.DISABLED, activebackground=theme.PANEL
            )

    def _tab_title(self, doc: Document) -> str:
        return ("\u2022 " if doc.dirty else "") + doc.path.name

    def _update_state(self) -> None:
        self._refresh_progress()
        self._refresh_tip()
        doc = self._doc
        has = doc is not None
        editing = has and doc.edit
        for button in self._doc_buttons:
            button.state(["!disabled"] if has else ["disabled"])
        for button in self._edit_buttons:
            button.state(["!disabled"] if editing else ["disabled"])
        self._btn_full.state(["!disabled"] if has and not editing else ["disabled"])
        for menu, index, gate in self._gated:
            ok = has and (gate == "doc" or (gate == "edit") == bool(editing))
            self._style_entry(menu, index, ok)
        for d in self._docs:
            self._tabs.set_title(d.uid, self._tab_title(d))

        if doc is None:
            self._info.set("")
            self._set_title("Boran")
            self._status.set("Open an image, drop one here, or use the folder panel on the left.")
            return
        sel = doc.selected
        self._info.set(doc.faces[sel].name or "Unnamed face" if sel is not None and 0 <= sel < len(doc.faces) else "")
        self._set_title(f"{'* ' if doc.dirty else ''}{doc.path.name} - Boran")
        named = sum(1 for f in doc.faces if f.name)
        busy = "  (detecting faces...)" if doc.detecting else ""
        hint = (
            "Click a face to name or rename it; right-click for more options."
            if doc.edit
            else "Hover a face to see the name. Turn on Edit mode (Ctrl+E) to change names."
        )
        unsaved = "  Unsaved: Ctrl+S saves to a .brn file." if doc.dirty else ""
        failed = f"  Face detection failed: {doc.detect_error}" if doc.detect_error else ""
        count = len(doc.faces)
        self._status.set(
            system.keys(
                f"{doc.path.name}: {count} face{'' if count == 1 else 's'}, {named} named{busy}. {hint}{unsaved}{failed}"
            )
        )

    # --- tips -------------------------------------------------------------
    def _notify(self, text: str, kind: str = "info") -> None:
        """Show a short message for five seconds; at most three show at once and the rest wait their turn."""
        self._snacks.show(system.keys(text), kind)

    def _tip_context(self) -> tips.Context:
        doc = self._doc
        if doc is None:
            return tips.Context(tabs=len(self._docs), tree_visible=self._tree_shown())
        return tips.Context(
            has_doc=True,
            editing=doc.edit,
            adding=doc.edit and self._add_mode.get(),
            full=self._full,
            dirty=doc.dirty,
            detecting=doc.detecting,
            faces=len(doc.faces),
            unnamed=sum(1 for f in doc.faces if not f.name),
            tabs=len(self._docs),
            fitted=self._view.get_state()[3],
            tree_visible=self._tree_shown(),
            siblings=len(self._siblings_of(doc)) > 1,
        )

    def _show_tip(self, tip: tips.Tip | None) -> None:
        self._tip_text.configure(text=system.keys(tip.text) if tip else "")
        if tip is not None and tip.keys:
            self._tip_keys.set_text(system.keys(tip.keys))
            self._tip_keys.pack(side="right", padx=(0, 6), before=self._status_label)
        else:
            self._tip_keys.pack_forget()

    def _restart_tip_timer(self) -> None:
        if self._tip_job is not None:
            self.after_cancel(self._tip_job)
        self._tip_job = self.after(_TIP_INTERVAL_MS, self._rotate_tip)

    def _refresh_tip(self) -> None:
        """Jump to the most useful tip as soon as what the user is doing changes."""
        tip = self._tips.update(self._tip_context())
        if tip is not None or self._tip_job is None:
            self._show_tip(tip)
            self._restart_tip_timer()

    def _rotate_tip(self) -> None:
        self._tip_job = None
        changed = self._tips.update(self._tip_context())  # picks up zoom changes, which don't trigger a state refresh
        self._show_tip(changed if changed is not None else self._tips.next())
        self._restart_tip_timer()

    # --- documents --------------------------------------------------------
    def _find(self, path: Path) -> Document | None:
        key = _key(path)
        return next((d for d in self._docs if _key(d.path) == key), None)

    def _by_uid(self, uid: int) -> Document | None:
        return next((d for d in self._docs if d.uid == uid), None)

    def _decode(self, path: Path) -> Document | None:
        brn: BrnFile | None = None
        try:
            if path.suffix.lower() == SUFFIX:
                brn = read_brn(path)
                image = formats.load(brn.image_bytes, brn.image_name)
                if image.size != brn.size:
                    raise BrnError("Image size does not match the file header")
            else:
                image = formats.load(path)
        except (OSError, ValueError, Image.DecompressionBombError, BrnError) as exc:
            messagebox.showwarning("Cannot open file", f"{path.name}: {exc}", parent=self)
            return None
        faces = list(brn.faces) if brn else []
        self._known_names.update(f.name for f in faces if f.name)
        return Document(
            uid=next(self._uids), path=path, image=image, faces=faces,
            image_name=brn.image_name if brn else path.name,
            image_bytes=brn.image_bytes if brn else None,
            edits=Edits.from_dict(brn.edits) if brn else Edits(),
            brn_path=path if brn else None,
            edit=not any(f.name for f in faces),  # unnamed photos open ready to edit
        )

    def open_path(self, path: Path, replace: bool = False) -> Document | None:
        """Open a file in a new tab (or reuse its tab). `replace` swaps the active tab when it has no unsaved changes."""
        path = Path(path)
        existing = self._find(path)
        if existing is not None:
            self._activate(existing)
            return existing
        doc = self._decode(path)
        if doc is None:
            return None
        old = self._doc if replace and self._doc is not None and not self._doc.dirty else None
        if old is not None:
            self._docs[self._docs.index(old)] = doc
            old.closed = True
            self._doc = None
            self._tabs.replace(old.uid, doc.uid, self._tab_title(doc))
        else:
            self._docs.append(doc)
            self._tabs.add(doc.uid, self._tab_title(doc))
        self._activate(doc)
        self._notify(f"Opened {doc.path.name}")
        if doc.brn_path is None:
            self._start_detection(doc)
            self._update_state()
        return doc

    def _activate(self, doc: Document) -> None:
        if doc is self._doc:
            self._update_state()
            return
        if self._doc is not None:
            self._doc.view = self._view.get_state()
        self._doc = doc
        self._tabs.select(doc.uid)
        self._view.set_image(doc.image, doc.view)
        self._view.set_faces(doc.faces)
        self._view.set_selected(doc.selected)
        self._add_mode.set(False)
        self._apply_mode()
        self._sync_edits()
        self._sync_tree()
        self._update_state()

    def _cycle_tab(self, delta: int) -> None:
        if self._doc is not None and len(self._docs) > 1:
            self._activate(self._docs[(self._docs.index(self._doc) + delta) % len(self._docs)])

    def _on_tab_select(self, uid: int) -> None:
        doc = self._by_uid(uid)
        if doc is not None:
            self._activate(doc)

    def _on_tab_close(self, uid: int) -> None:
        doc = self._by_uid(uid)
        if doc is not None:
            self._close(doc)

    def _close_active(self) -> None:
        if self._doc is not None:
            self._close(self._doc)

    def _close(self, doc: Document) -> bool:
        if doc.dirty and not self._confirm_discard(doc):
            return False
        index = self._docs.index(doc)
        doc.closed = True
        self._docs.remove(doc)
        self._tabs.remove(doc.uid)
        if doc is self._doc:
            self._doc = None
            if self._docs:
                self._activate(self._docs[min(index, len(self._docs) - 1)])
            else:
                self._view.set_image(None)
                self._view.set_faces([])
                self._apply_mode()
                self._sync_edits()
        self._update_state()
        return True

    def _siblings_of(self, doc: Document) -> list[Path]:
        """Supported files in the document's folder, sorted by name; listed once per folder."""
        cached = self._sib_cache
        if cached is None or cached[0] != doc.path.parent or doc.path not in cached[1]:
            try:
                supported = _open_extensions()
                items = sorted(
                    (p for p in doc.path.parent.iterdir() if p.suffix.lower() in supported),
                    key=lambda p: p.name.lower(),
                )
            except OSError:
                items = [doc.path]
            cached = self._sib_cache = (doc.path.parent, items)
        return cached[1]

    def _step(self, delta: int) -> None:
        doc = self._doc
        if doc is None:
            return
        siblings = self._siblings_of(doc)
        i = siblings.index(doc.path) + delta if doc.path in siblings else -1
        if 0 <= i < len(siblings):
            self.open_path(siblings[i], replace=True)

    def _arrow(self, delta: int) -> None:
        try:
            focused = self.focus_get()
        except KeyError:
            focused = None
        if not isinstance(focused, (ttk.Treeview, tk.Entry, ttk.Entry, ttk.Combobox)):
            self._step(delta)

    # --- edit panel -------------------------------------------------------
    def _apply_dock(self) -> None:
        if self._dock_var.get():
            self._dock.show()
        else:
            self._dock.hide()

    def _on_dock_change(self, opened: bool, section: str | None) -> None:
        self._dock_var.set(opened)
        if opened and section == "looks":
            self._looks.ensure_thumbnails()

    @staticmethod
    def _pixel_filter(edits: Edits):
        if edits.is_identity():
            return None
        return lambda image, region, scale: apply_edits(image, edits, region, scale)

    def _sync_edits(self) -> None:
        """Show the active tab's edits in the panels and on the photo."""
        doc = self._doc
        edits = doc.edits if doc else None
        self._adjust.load(edits)
        self._looks.load(edits, doc.image if doc else None)
        if self._dock.is_open and self._dock.active == "looks":
            self._looks.ensure_thumbnails()
        self._view.set_filter(self._pixel_filter(edits) if edits else None)

    def _update_edits(self, change) -> None:
        doc = self._doc
        if doc is None:
            return
        doc.edits = change(doc.edits)
        self._view.set_filter(self._pixel_filter(doc.edits))
        if not doc.dirty:
            doc.dirty = True
            self._update_state()

    def _view_compare(self, on: bool) -> None:
        self._view.set_compare(on)

    def _reset_edits(self) -> None:
        doc = self._doc
        if doc is None or doc.edits.is_identity():
            return
        doc.edits = Edits()
        doc.dirty = True
        self._sync_edits()
        self._update_state()
        self._notify("Back to the original photo")

    # --- folder panel -----------------------------------------------------
    def _tree_shown(self) -> bool:
        return str(self._tree) in {str(p) for p in self._paned.panes()}

    def _apply_tree(self) -> None:
        show = self._tree_var.get() and not self._full
        shown = self._tree_shown()
        if show and not shown:
            if self._tree.root_path is None:
                self._tree.set_root(self._doc.path.parent if self._doc else self._default_root())
            self._paned.add(self._tree, before=self._right, minsize=180, width=260, stretch="never")
            self._sync_tree()
        elif not show and shown:
            self._paned.forget(self._tree)

    @staticmethod
    def _default_root() -> Path:
        pictures = Path.home() / "Pictures"
        return pictures if pictures.is_dir() else Path.home()

    def _sync_tree(self) -> None:
        if self._doc is None or not self._tree_shown():
            return
        root = self._tree.root_path
        if root is None or not self._doc.path.is_relative_to(root):
            self._tree.set_root(self._doc.path.parent)
        self._tree.reveal(self._doc.path)

    def _open_folder(self) -> None:
        self._tree_var.set(True)
        self._apply_tree()
        self._tree.choose_folder()

    # --- opening ----------------------------------------------------------
    def _enable_drop(self) -> None:
        if DND_FILES is None:
            return
        for widget in (
            self, self._top, self._tabs, self._view, self._tree.tree,
            self._status_bar, self._status_label, self._tip_text,
        ):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event) -> str:
        files = [p for p in map(Path, self.tk.splitlist(event.data)) if p.is_file()]
        supported = _open_extensions()
        picked = [p for p in files if p.suffix.lower() in supported] or files[:1]
        if not picked:
            self._notify("Drop an image file to open it.", "warning")
        else:
            def open_all() -> None:  # after Explorer's drag has finished
                for p in picked[:_MAX_OPEN_AT_ONCE]:
                    self.open_path(p)

            self.after(0, open_all)
        return event.action

    def _open_dialog(self) -> None:
        patterns = " ".join(f"*{e}" for e in sorted(_open_extensions()))
        start = str(self._doc.path.parent) if self._doc else None
        names = filedialog.askopenfilenames(
            parent=self, title="Open", initialdir=start,
            filetypes=[("Boran files and images", patterns), ("Boran files", f"*{SUFFIX}"), ("All files", "*.*")],
        )
        for name in self.tk.splitlist(names)[:_MAX_OPEN_AT_ONCE]:
            self.open_path(Path(name))

    # --- detection (background) -------------------------------------------
    @staticmethod
    def _prewarm_detector() -> None:
        """Load OpenCV and the image codecs in the background while the user picks a photo."""
        formats.supported_extensions()
        try:
            import cv2  # noqa: F401
        except ImportError:
            pass

    def _progress_active(self) -> bool:
        """True only while the detector is running on the active tab."""
        doc = self._doc
        return doc is not None and doc.detecting and doc.progress is not None and doc.progress[0] == doc.det_token

    def _refresh_progress(self) -> None:
        if not self._progress_active():
            if self._progress_panel.winfo_ismapped():
                self._progress_panel.place_forget()
            return
        assert self._doc is not None and self._doc.progress is not None
        _, fraction, text = self._doc.progress
        self._progress_bar["value"] = fraction * 100
        self._progress_detail.config(text=f"{text}  |  {fraction * 100:.0f}%")
        if not self._progress_panel.winfo_ismapped():
            self._progress_panel.place(relx=0.5, rely=1.0, y=-24, anchor="s")

    def _start_detection(self, doc: Document) -> None:
        doc.det_token += 1
        token, image = doc.det_token, doc.image
        doc.detecting = True
        doc.progress = None
        doc.detect_error = None

        def work() -> None:
            def report(fraction: float, text: str) -> None:
                doc.progress = (token, fraction, text)

            try:
                from boran.detector import detect_faces

                self._results.put((doc, token, detect_faces(image, report), None))
            except ImportError as exc:
                self._results.put((doc, token, [], f"OpenCV is not installed for {sys.executable} ({exc})"))
            except Exception as exc:  # detection failure must not block manual naming
                self._results.put((doc, token, [], str(exc)))

        threading.Thread(target=work, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.after(50, self._poll)

    def _poll(self) -> None:
        while True:
            try:
                doc, token, found, error = self._results.get_nowait()
            except queue.Empty:
                break
            if doc.closed or token != doc.det_token:
                continue
            doc.detecting = False
            if error:
                doc.progress = None
                doc.detect_error = error
                self._update_state()
                self._notify(f"{doc.path.name}: face detection failed", "error")
                if not self._warned_detect:
                    self._warned_detect = True
                    messagebox.showwarning(
                        "Face detection failed",
                        f"{error}\n\nYou can still add faces by hand with Add face.\n"
                        "If OpenCV is missing, start the app with the project's virtual environment:\n"
                        + (".venv\\Scripts\\python.exe -m boran" if system.IS_WIN else ".venv/bin/python -m boran"),
                        parent=self,
                    )
                continue
            added = 0
            for face in found:
                if all(iou(face, e) < _DUPLICATE_IOU for e in doc.faces):
                    doc.faces.append(face)
                    added += 1
            if added:
                self._notify(f"{doc.path.name}: {added} face{'' if added == 1 else 's'} detected", "success")
            else:
                self._notify(f"{doc.path.name}: no new faces found. Press Ctrl+D to add one by hand", "warning")
            if doc is self._doc:
                self._view.refresh()
            self._update_state()
        self._refresh_progress()
        if any(d.detecting for d in self._docs):
            self.after(50, self._poll)
        else:
            self._polling = False

    # --- editing ----------------------------------------------------------
    def _select(self, index: int | None) -> None:
        if self._doc is not None:
            self._doc.selected = index
        self._view.set_selected(index)

    def _editing(self) -> bool:
        return self._doc is not None and self._doc.edit

    def _on_face_click(self, index: int | None) -> None:
        self._select(index)
        self._update_state()
        if index is not None and self._editing():
            self._rename(index)

    def _rename(self, index: int) -> None:
        if not self._editing() or not 0 <= index < len(self._faces):
            return
        self._select(index)
        name = ask_name(self, self._faces[index].name, self._known_names)
        if name is None:
            return
        self._faces[index].name = name
        if name:
            self._known_names.add(name)
        self._commit()
        self._notify(f"Named face: {name}" if name else "Name cleared", "success")

    def _show_menu(self, index: int, x: int, y: int) -> None:
        if not self._editing() or not 0 <= index < len(self._faces):
            return
        self._select(index)
        self._update_state()
        menu = DarkMenu(self, font=theme.MENU_FONT)
        menu.add_command(label="Rename...", command=lambda: self._rename(index))
        menu.add_command(label="Clear name", command=lambda: self._set_name(index, "") if self._faces[index].name else None)
        self._style_entry(menu, menu.index("end"), bool(self._faces[index].name))
        menu.add_separator()
        menu.add_command(label="Delete face", command=lambda: self._delete_face(index))
        popup(menu, x, y)

    def _set_name(self, index: int, name: str) -> None:
        if 0 <= index < len(self._faces):
            self._faces[index].name = name
            self._commit()
            self._notify("Name cleared" if not name else f"Named face: {name}", "success")

    def _delete_face(self, index: int) -> None:
        if 0 <= index < len(self._faces):
            del self._faces[index]
            self._select(None)
            self._commit()
            self._notify("Face deleted")

    def _add_face(self, x: int, y: int, w: int, h: int) -> None:
        if self._doc is None:
            return
        self._faces.append(FaceBox(x, y, w, h))
        self._commit()
        self._notify("Face added")
        self._rename(len(self._faces) - 1)

    def _redetect(self) -> None:
        doc = self._doc
        if doc is None or not doc.edit:
            return
        if doc.faces and not messagebox.askyesno(
            "Re-detect faces", "This replaces all current boxes and names. Continue?", parent=self
        ):
            return
        doc.faces.clear()
        self._select(None)
        self._start_detection(doc)
        self._commit()
        self._notify(f"{doc.path.name}: detecting faces again")

    def _commit(self) -> None:
        if self._doc is not None:
            self._doc.dirty = True
        self._view.refresh()
        self._update_state()

    # --- saving -----------------------------------------------------------
    def _image_data(self, doc: Document) -> bytes | None:
        """Original encoded image bytes, read once and kept for saving."""
        if doc.image_bytes is None:
            try:
                doc.image_bytes = doc.path.read_bytes()
            except OSError as exc:
                messagebox.showwarning("Save failed", f"Cannot read {doc.path.name}: {exc}", parent=self)
        return doc.image_bytes

    def _save(self, save_as: bool = False, doc: Document | None = None) -> bool:
        """Write photo + faces + names into one .brn file. Returns True if saved."""
        doc = doc or self._doc
        if doc is None:
            return False
        target = doc.brn_path
        if save_as or target is None:
            picked = filedialog.asksaveasfilename(
                parent=self, title="Save as Boran file", defaultextension=SUFFIX,
                initialdir=str(doc.path.parent), initialfile=Path(doc.image_name).stem + SUFFIX,
                filetypes=[("Boran file", f"*{SUFFIX}")],
            )
            if not picked:
                return False
            target = Path(picked)
            if target.suffix.lower() != SUFFIX:  # never overwrite a photo
                target = target.with_name(target.name + SUFFIX)
        data = self._image_data(doc)
        if data is None:
            return False
        try:
            write_brn(
                target, data, doc.image_name, doc.image.size, doc.faces,
                None if doc.edits.is_identity() else doc.edits.to_dict(),
            )
        except BrnError as exc:
            messagebox.showwarning("Save failed", str(exc), parent=self)
            return False
        doc.brn_path = target
        doc.dirty = False
        self._update_state()
        self._notify(f"Saved {target.name}", "success")
        return True

    def _confirm_discard(self, doc: Document) -> bool:
        """Ask what to do with a tab's unsaved changes. True means it is safe to continue."""
        self._activate(doc)
        answer = messagebox.askyesnocancel(
            "Unsaved changes", f"Save the faces, names and edits of {doc.path.name} to a .brn file first?", parent=self
        )
        if answer is None:
            return False
        return self._save(doc=doc) if answer else True

    def _on_close(self) -> None:
        for doc in list(self._docs):
            if doc.dirty and not self._confirm_discard(doc):
                return
        self.destroy()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Boran.App")  # own taskbar icon, not python.exe's
        except (AttributeError, OSError):
            pass
    initial = Path(args[1]) if len(args) > 1 else None
    App(initial if initial and initial.is_file() else None).mainloop()
    return 0
