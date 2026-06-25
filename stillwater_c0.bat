@echo off
rem CONTEMPT A/B control arm: shipped tuned constants, DirectML, DrawContempt=0
rem (the CURRENT live behavior -- the conversion fix is not deployed). No visit-
rem readout, no policy-tiebreak. Test harness only (not the live bot config).
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
set STILLWATER_DRAW_CONTEMPT=0.0
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
