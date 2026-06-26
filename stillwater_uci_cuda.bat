@echo off
rem STILLWATER UCI launcher -- CUDA DEPLOY variant of stillwater_uci.bat.
rem Identical tuned constants and behavior to the live DirectML launcher; the ONLY
rem difference is the backend: the sw-gpu-venv interpreter, which resolves to the
rem CUDAExecutionProvider. CUDA is LEAK-SAFE here because STILLWATER_CUDA_FAST is
rem NOT set -> oracle.py uses the memory-bounded arena (kSameAsRequested + bounded
rem workspace), which does not grow GPU memory across a long-running bot session
rem (the FAST path leaks ~1GB/100k inferences and is gauntlet-only). Throughput is
rem higher than DirectML; this is the no-regret throughput slice of the lc0 gap.
rem GO-LIVE: point the lichess-bot engine command at THIS bat instead of
rem stillwater_uci.bat, then restart the bot. Validated by the anti-drift gauntlet,
rem which runs this same CUDA path (sw_cuda_base.bat).
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
"C:\Users\nonna\Downloads\sw-gpu-venv\Scripts\python.exe" -u -m stillwater.uci
