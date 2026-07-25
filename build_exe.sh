#!/usr/bin/env bash
# build_exe.sh
# Builds a standalone stillwater binary using PyInstaller, for use with
# UCI-compatible GUIs (En Croissant, Arena, BanksiaGUI, cutechess, etc.)
#
# Run this from the repo root.
#
# NOTE: onnxruntime-directml is Windows-only. On Linux/Mac, swap in
# onnxruntime (CPU) or onnxruntime-gpu in requirements before running this,
# or the resulting binary will fail to load the network at runtime.

set -e

echo "=== Installing build dependencies ==="
pip install pyinstaller

echo "=== Building stillwater binary (see stillwater.spec) ==="
pyinstaller --clean stillwater.spec

echo ""
echo "=== Build complete ==="
echo "Binary + nets folder are in: dist/stillwater/"
echo "Point your GUI (e.g. En Croissant) at dist/stillwater/stillwater"
