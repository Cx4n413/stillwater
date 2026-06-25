@echo off
rem CONTEMPT A/B treatment arm: shipped tuned constants, DirectML, DrawContempt=
rem 0.10 (the validated-but-unshipped conversion fix). No visit-readout, no
rem policy-tiebreak. Identical to stillwater_c0.bat except the contempt value.
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
set STILLWATER_DRAW_CONTEMPT=0.10
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
