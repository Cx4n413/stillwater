@echo off
rem CANDIDATE engine launcher for gauntlets: shipped tuned constants + TensorRT
rem (leak-free) + the gated policy-aware tie-break readout (eps=0.05) + the
rem DrawContempt conversion fix. Single-command launcher (cutechess cmd=this.bat,
rem no args) so the harness can't mis-parse a python -m arg string. NOT the live
rem bot launcher (that is stillwater_uci.bat); this is the experimental candidate.
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
set STILLWATER_TRT=1
set STILLWATER_POL_TIEBREAK=0.05
set STILLWATER_DRAW_CONTEMPT=0.10
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
