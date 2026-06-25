@echo off
rem A/B BASELINE arm: shipped tuned constants + DrawContempt, DirectML, NO
rem visit-readout, NO policy-tiebreak. The control for the structure-lever
rem gauntlet (vs stillwater_vison.bat). Single-command launcher for cutechess.
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
