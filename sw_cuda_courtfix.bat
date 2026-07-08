@echo off
rem BISECT ARM B: deployed constants + COURT FIXES ONLY (no Aquifer, no bank).
rem Isolates the arbiter-mode delusion trigger: if this arm goes delusional,
rem the court fixes (FRESH_P/MIN_SPEND) amplify the latent proof bug; if sane,
rem the Aquifer is indicted.
set STILLWATER_CONVERT=1
set STILLWATER_VERIFY_DRAW=256
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
set STILLWATER_MIN_SPEND=0.35
set STILLWATER_FRESH_P=1
cd /d "%~dp0"
"C:\Users\nonna\Downloads\sw-gpu-venv\Scripts\python.exe" -u -m stillwater.uci
