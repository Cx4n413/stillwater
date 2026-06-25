@echo off
rem STILLWATER on the CUDA venv -- ANTI-DRIFT arm. Identical to sw_cuda_base.bat
rem plus the signal-gated anti-drift readout. DELTA/EFLOOR overridable by the
rem caller's environment (set them before launch to sweep); defaults here.
set STILLWATER_CONVERT=1
set STILLWATER_VERIFY_DRAW=256
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
set STILLWATER_ANTIDRIFT=1
if "%STILLWATER_DRIFT_DELTA%"=="" set STILLWATER_DRIFT_DELTA=0.12
if "%STILLWATER_DRIFT_EFLOOR%"=="" set STILLWATER_DRIFT_EFLOOR=3000
cd /d "%~dp0"
"C:\Users\nonna\Downloads\sw-gpu-venv\Scripts\python.exe" -u -m stillwater.uci
