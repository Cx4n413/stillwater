@echo off
rem Tactical A/B: WAC-300 at 1000ms, Refine off (old) then on (new).
rem Sequential - one GPU. Harvest/Ledger off in the bench itself.
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
cd /d %REPO%
echo === TACT AB starting %DATE% %TIME% === > "%REPO%\games\tact_ab.log"
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --tag old >> "%REPO%\games\tact_ab.log" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --tag new >> "%REPO%\games\tact_ab.log" 2>&1
echo TACT AB DONE %DATE% %TIME% >> "%REPO%\games\tact_ab.log"
