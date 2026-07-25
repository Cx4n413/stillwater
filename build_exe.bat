@echo off
REM build_exe.bat
REM Builds a standalone stillwater.exe using PyInstaller, for use with
REM UCI-compatible GUIs (En Croissant, Arena, BanksiaGUI, cutechess, etc.)
REM
REM Run this from the repo root.

setlocal

echo === Installing build dependencies ===
pip install pyinstaller
if errorlevel 1 goto :error

echo === Building stillwater.exe (see stillwater.spec) ===
pyinstaller --clean stillwater.spec
if errorlevel 1 goto :error

echo.
echo === Build complete ===
echo Binary + nets folder are in: dist\stillwater\
echo Point your GUI (e.g. En Croissant) at dist\stillwater\stillwater.exe
goto :eof

:error
echo.
echo === Build failed, see errors above ===
exit /b 1
