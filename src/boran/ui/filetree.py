from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from boran import formats
from boran.brn import SUFFIX
from boran.ui import theme
from boran.ui.ribbon import RibbonButton

_PLACEHOLDER = "\0"


class FileTree(tk.Frame):
    """Folder panel: browse a folder and double-click an image to open it in a new tab."""

    def __init__(self, master, on_open: Callable[[Path], object]):
        super().__init__(master, bg=theme.PANEL)
        self._on_open = on_open
        self.root_path: Path | None = None

        header = tk.Frame(self, bg=theme.PANEL)
        header.pack(side="top", fill="x")
        self._title = tk.Label(header, text="FOLDER", font=(theme.SYSTEM_FONT, 8, "bold"), fg=theme.MUTED, bg=theme.PANEL, anchor="w")
        self._title.pack(side="left", padx=10)
        RibbonButton(header, "Up", self.go_up, "\uE74A", compact=True, tip="Parent folder").pack(side="right")
        RibbonButton(header, "Open", self.choose_folder, "\uE838", compact=True, tip="Open folder...").pack(side="right")

        body = tk.Frame(self, bg=theme.PANEL)
        body.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(body, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("dir", foreground="#e5c07b")
        self.tree.tag_configure("brn", foreground="#7bd88f")

        self.tree.bind("<<TreeviewOpen>>", self._on_expand)
        self.tree.bind("<Double-Button-1>", self._on_double)
        self.tree.bind("<Return>", self._on_return)

    # --- root handling ----------------------------------------------------
    def set_root(self, path: Path) -> None:
        self.root_path = path
        self.tree.delete(*self.tree.get_children())
        self._title.configure(text=(path.name or str(path)).upper())
        iid = str(path)
        self.tree.insert("", "end", iid=iid, text=path.name or str(path), tags=("dir",))
        self._populate(iid)
        self.tree.item(iid, open=True)

    def go_up(self) -> None:
        if self.root_path is not None and self.root_path.parent != self.root_path:
            self.set_root(self.root_path.parent)

    def choose_folder(self) -> None:
        start = str(self.root_path) if self.root_path else None
        chosen = filedialog.askdirectory(parent=self.winfo_toplevel(), title="Open folder", initialdir=start)
        if chosen:
            self.set_root(Path(chosen))

    def reveal(self, path: Path) -> None:
        """Expand folders down to `path` and select it, if it is inside the current root."""
        root = self.root_path
        if root is None:
            return
        try:
            relative = path.relative_to(root)
        except ValueError:
            return
        node = root
        for part in relative.parts[:-1]:
            node = node / part
            if not self.tree.exists(str(node)):
                return
            self._populate(str(node))
            self.tree.item(str(node), open=True)
        if self.tree.exists(str(path)):
            self.tree.selection_set(str(path))
            self.tree.see(str(path))

    # --- loading ----------------------------------------------------------
    def _populate(self, iid: str) -> None:
        """(Re)build the children of a folder node."""
        children = self.tree.get_children(iid)
        if children and not (len(children) == 1 and children[0].endswith(_PLACEHOLDER)):
            return  # already loaded
        self.tree.delete(*children)
        supported = formats.supported_extensions() | {SUFFIX}
        folders: list[os.DirEntry] = []
        files: list[os.DirEntry] = []
        try:
            with os.scandir(iid) as entries:
                for entry in entries:
                    if entry.name.startswith((".", "$")):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry)
                    elif Path(entry.name).suffix.lower() in supported:
                        files.append(entry)
        except OSError:
            return
        for entry in sorted(folders, key=lambda e: e.name.lower()):
            self.tree.insert(iid, "end", iid=entry.path, text=entry.name, tags=("dir",))
            self.tree.insert(entry.path, "end", iid=entry.path + _PLACEHOLDER, text="")
        for entry in sorted(files, key=lambda e: e.name.lower()):
            tag = "brn" if entry.name.lower().endswith(SUFFIX) else "file"
            self.tree.insert(iid, "end", iid=entry.path, text=entry.name, tags=(tag,))

    def _on_expand(self, _event) -> None:
        iid = self.tree.focus()
        if iid:
            self._populate(iid)

    def _open_item(self, iid: str) -> None:
        path = Path(iid)
        if path.is_file():
            self._on_open(path)
        elif self.tree.exists(iid):
            self._populate(iid)
            self.tree.item(iid, open=not self.tree.item(iid, "open"))

    def _on_double(self, event) -> str:
        iid = self.tree.identify_row(event.y)
        if iid:
            self._open_item(iid)
        return "break"  # stop the default expand/collapse toggle

    def _on_return(self, _event) -> None:
        iid = self.tree.focus()
        if iid:
            self._open_item(iid)
