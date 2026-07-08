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
rem THE AQUIFER (see stillwater_uci.bat): compounding opening outcome-memory.
rem AQUIFER PULLED 2026-07-07: indicted by bisect -- the arbiter-mode gauntlet
rem went delusional ONLY with this flag (arms without it sane). Mechanism not yet
rem understood -> off everywhere until it is. Re-enable only after root-cause + gate.
set STILLWATER_AQUIFER=0
rem COURT FIX (2026-07-07 audit): the ceiling match was lost substantially on
rem blitzed moves (27% of moves <0.5s; 10/12 losing decisions under-thought) and
rem carried-DAG confidence (3 losing moves reproduce ONLY with the carried
rem lattice). MIN_SPEND: invest >=35% of the soft budget on any non-lost,
rem unproven root before a confidence stop. FRESH_P: stopping confidence counts
rem only THIS move's evals -- carried beliefs steer, they don't testify.
set STILLWATER_MIN_SPEND=0.35
set STILLWATER_FRESH_P=1
rem BANK-SPEND: convert clock surplus into search. OFF for the 100-games/day
rem push (2026-07-08): it added 5-8 min of OUR clock to every game while the
rem flat time-curve gains little from it (we held SF18 at ~2s/move without it).
rem Throughput = games/day; strength cost is minimal by measurement.
set STILLWATER_BANK_SPEND=0.0
cd /d "%~dp0"
"C:\Users\nonna\Downloads\sw-gpu-venv\Scripts\python.exe" -u -m stillwater.uci
