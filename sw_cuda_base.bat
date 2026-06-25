@echo off
rem STILLWATER on the CUDA venv (fast gauntlets) -- BASELINE arm (anti-drift OFF).
rem Deployed tuned constants (mirrors stillwater_uci.bat). Net comes via the
rem cutechess option.NetPath so the broken v3 ft-net is never auto-discovered.
set STILLWATER_CONVERT=1
set STILLWATER_VERIFY_DRAW=256
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
cd /d "%~dp0"
"C:\Users\nonna\Downloads\sw-gpu-venv\Scripts\python.exe" -u -m stillwater.uci
