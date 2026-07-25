# stillwater.spec
#
# PyInstaller spec file to build a standalone stillwater.exe (Windows) /
# stillwater binary (Linux/Mac) that speaks UCI, for use with GUIs like
# En Croissant, Arena, BanksiaGUI, cutechess, etc.
#
# Usage:
#   pip install pyinstaller
#   pyinstaller stillwater.spec
#
# Output lands in dist/stillwater/stillwater.exe (onedir build — see notes
# at the bottom for why onedir instead of onefile).

# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Bundle the nets/ directory (ONNX weights) alongside the exe so the built
# binary is drop-in runnable without needing the source tree present.
# Adjust the source path if the actual weights directory differs.
datas = [
    (os.path.join("nets"), "nets"),
]

# onnxruntime-directml ships its own DLLs that PyInstaller's hook doesn't
# always catch automatically -- collect them explicitly to avoid a
# "DLL load failed" error on a machine without a dev Python install.
try:
    from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
    binaries = collect_dynamic_libs("onnxruntime")
    datas += collect_data_files("onnxruntime")
except Exception:
    binaries = []

a = Analysis(
    ["stillwater/uci.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "chess",
        "chess.polyglot",
        "numpy",
        "onnxruntime",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="stillwater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # UCI engines talk over stdin/stdout -- must stay a console app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="stillwater",
)

# --- Notes ---
# 1. onedir (COLLECT) vs onefile: onefile unpacks to a temp dir on every
#    launch, which adds a multi-second startup delay -- painful for a UCI
#    engine that a GUI may restart often. onedir starts instantly after the
#    first run and is the standard choice for engine binaries. Trade-off is
#    you distribute a folder instead of a single file; zip it for releases.
#
# 2. Update the Analysis() entry script path if the actual UCI entry point
#    isn't stillwater/uci.py -- e.g. if it's exposed as a console_script via
#    setup.py/pyproject.toml instead, point this at that wrapper script.
#
# 3. onnxruntime-directml requires Windows + DirectX 12 capable GPU/driver;
#    this build targets Windows only for now. A CPU-only onnxruntime build
#    would be needed for a Linux/Mac release.
