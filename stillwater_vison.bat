@echo off
rem A/B CANDIDATE arm: baseline config + the STRUCTURE LEVER (visit-distribution
rem readout, band 0.15). Identical to stillwater_visoff.bat except VISIT_READOUT
rem on. The only difference from the control is the final move-readout.
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
set STILLWATER_DRAW_CONTEMPT=0.10
set STILLWATER_VISIT_READOUT=1
set STILLWATER_VIS_BAND=0.15
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
