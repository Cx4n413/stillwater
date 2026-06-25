@echo off
rem #90 TREATMENT launcher: deployed config + the max-backup-native value head.
rem STILLWATER_VHEAD=1 makes the oracle load nets/BT4-embed.onnx and replace the
rem value (W-L) with the trained head (nets/value_head_v1.npz), keeping native D.
rem Unset it (or use stillwater_uci.bat) for the byte-identical baseline arm.
set STILLWATER_VHEAD=1
rem --- deployed config (must match stillwater_uci.bat exactly) ---
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
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
