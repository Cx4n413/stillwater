@echo off
rem STILLWATER with the shelved STS-tuned constant vector (never game-validated).
rem Tuner result: STS-1500 85.87->86.96 (+1.09), WAC 92.0->91.33. Notably lcb_k 0->
rem the tuner wanted LESS search-pessimism (opposite of the failed honest-max).
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
