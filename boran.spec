# Build: python -m PyInstaller boran.spec --noconfirm   (dist/Boran.exe on Windows, dist/Boran.app on macOS)
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("src/boran/models/*.onnx", "boran/models"),
    ("src/boran/fonts/*", "boran/fonts"),
]
datas += collect_data_files("tkinterdnd2")

# formats.py imports these lazily, so PyInstaller cannot see them
hiddenimports = ["pillow_heif"] + collect_submodules("boran")

a = Analysis(
    ["src/boran/__main__.py"],
    pathex=["src"],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "matplotlib", "scipy", "pandas"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Boran", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="Boran", upx=False)
    app = BUNDLE(
        coll,
        name="Boran.app",
        bundle_identifier="com.boran.app",
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "0.1.0"},
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name="Boran",
        console=False,
        upx=False,
    )
