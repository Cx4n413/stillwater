@echo off
rem ============================================================================
rem  HONEST-MAX strength sweep: WAC-300 @1s across STILLWATER_HONEST_K.
rem  honest_k=0.0 == the PREVIOUS version (bit-identical; if honest_k>0 short-
rem  circuits). Finds the strength that holds/improves tactics (non-destructive)
rem  before the game-level A/B match. The winner's-curse correction targets the
rem  9.7%% search-hurt; WAC mainly checks it doesn't BREAK tactics + the curve.
rem ============================================================================
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\honest_sweep.log
cd /d "%REPO%"
echo === HONEST-MAX WAC SWEEP start %DATE% %TIME% === > "%LOG%"

set STILLWATER_HONEST_K=0.0
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --tag hk000_wac >> "%LOG%" 2>&1
set STILLWATER_HONEST_K=0.05
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --tag hk005_wac >> "%LOG%" 2>&1
set STILLWATER_HONEST_K=0.10
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --tag hk010_wac >> "%LOG%" 2>&1
set STILLWATER_HONEST_K=0.15
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --tag hk015_wac >> "%LOG%" 2>&1
set STILLWATER_HONEST_K=0.25
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --tag hk025_wac >> "%LOG%" 2>&1

echo === HONEST-MAX WAC SWEEP COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
