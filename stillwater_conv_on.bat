@echo off
rem STILLWATER launcher WITH the conversion fix (STILLWATER_CONVERT=1): Syzygy
rem DTZ-optimal play in <=5-man TB wins (#1) + an endgame king-drive/progress
rem readout (#2) so dead-won endgames are converted instead of shuffled into a
rem 3-fold. Identical to stillwater_uci.bat in every other respect (the same
rem +34.9 Elo tuned constants). Used as the TREATMENT arm in the convert A/B;
rem stillwater_uci.bat is the control (convert off).
set STILLWATER_CONVERT=1
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
