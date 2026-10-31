# Boran

**Click the faces in a photo to name the people.**

Boran finds the faces in your photos, lets you put a name on each one, and saves everything, photo included,
into a single shareable `.brn` file. Open that file anywhere and the names are right there on the faces.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)

---

## Features

- **Automatic face detection** using the bundled YuNet model. It runs fully offline, and nothing is uploaded.
- **Click to name.** Switch on Edit mode, click a face and type a name. Add boxes the detector missed by drawing them.
- **One-file sharing.** The `.brn` file holds the original photo, the face boxes and the names. See [The .brn file](#the-brn-file).
- **Tabs and a folder panel** for working through many photos, with Left / Right to move between images in a folder.
- **Non-destructive edits.** Exposure, contrast, colour and detail sliders plus one-click looks (Vivid, Noir, Cinematic,
  Golden Hour and more). The original photo is never changed, and *Hold to compare* shows the before.
- **Full View presentation mode.** Show just the image full screen. Hover a face to reveal the name as a styled,
  animated title, or as a label on each face. Fonts, shapes, colours, motion and easing are all configurable.
- **Wide format support.** Everything Pillow reads, plus HEIC / HEIF / AVIF, and optionally JPEG XL and camera RAW.
- **Dark, drag-and-drop interface.** Drop photos onto the window to open them.

## Install

Requires **Python 3.10 or newer** with Tk (included with the python.org installers; on macOS with Homebrew,
`brew install python-tk`).

```bash
git clone https://github.com/gouthamreddymr/boran.git
cd boran
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

Optional formats:

```bash
pip install -e ".[jxl]"   # JPEG XL
pip install -e ".[raw]"   # camera RAW
```

## Run

```bash
python -m boran              # start empty
python -m boran photo.jpg    # open a photo (or a .brn file)
```

## Using Boran

1. **Open** a photo (`Ctrl/Cmd+O`), a folder (`Ctrl/Cmd+Shift+O`), or drop files on the window.
2. Boran detects faces in the background and shows a progress bar.
3. Turn on **Edit mode** (`Ctrl/Cmd+E`) and click a face to name it. Right-click a face for more options.
4. **Save** (`Ctrl/Cmd+S`) to write a `.brn` file you can share.
5. Press **F11** for Full View and hover faces to show the names.

### Keyboard shortcuts

On macOS, use **Cmd** where this table says **Ctrl** (except `Ctrl+Tab`).

| Action | Shortcut |
|---|---|
| Open images / Open folder | `Ctrl+O` / `Ctrl+Shift+O` |
| Save / Save As | `Ctrl+S` / `Ctrl+Shift+S` |
| Close tab | `Ctrl+W` |
| Edit mode | `Ctrl+E` |
| Add face (draw a box) | `Ctrl+D` |
| Re-detect faces | `Ctrl+R` |
| Folder panel / Edit panel | `Ctrl+B` / `Ctrl+J` |
| Next / previous tab | `Ctrl+Tab` / `Ctrl+Shift+Tab` |
| Previous / next image in folder | `Left` / `Right` |
| Fit / 100% / Zoom in / Zoom out | `0` / `1` / `+` / `-` |
| Full View / exit | `F11` / `Esc` |
| Full View: one title or a label per face | `T` |

## The .brn file

A `.brn` file is a single binary container:

```
magic (8) | version (2) | header length (4) | image length (8) | header (JSON) | image bytes
```

- The **image** is the original file, byte for byte, so the `.brn` opens without the photo on disk.
- The **header** is JSON: image name and size, a SHA-256 of the image, the face boxes with their names, and any edits.
- Saves are atomic, and loading validates every field and the image hash, so a corrupt file is rejected rather than half-opened.
- Because the original file is kept as is, any EXIF data in the photo (for example GPS location) is shared too.

The format is defined in [src/boran/brn.py](src/boran/brn.py).

## Build a standalone app

```bash
pip install pyinstaller
python -m PyInstaller boran.spec --noconfirm
```

| Platform | Output |
|---|---|
| Windows | `dist/Boran.exe` (single file) |
| macOS | `dist/Boran.app` |

Close any running copy of the app before rebuilding on Windows, or the build can't overwrite the exe.

## Project layout

```
src/boran/
  app.py          main window and application logic
  brn.py          the .brn file format
  detector.py     face detection (OpenCV YuNet)
  formats.py      image decoding and optional plugins
  edits.py        adjustments and looks
  title_style.py  Full View title settings
  ui/             widgets, theme, menus, dialogs
  models/         bundled face-detection model
  fonts/          bundled Google Sans font (OFL)
boran.spec        PyInstaller build recipe
```

## Platform notes

- **Windows** is the primary platform and uses a custom dark title bar.
- **macOS** uses the native title bar and Cmd shortcuts. Support is new and has had less testing than Windows.
  Please report anything that looks or behaves oddly.

## License

The bundled Google Sans font is licensed under the SIL Open Font License; see
[src/boran/fonts/OFL.txt](src/boran/fonts/OFL.txt).
