@echo off
rem ARM C, iteration 2: C6 = C5 + ml_thresh 0.5 (conversion urgency fires
rem from +0.5 instead of lc0's 0.8 — our max-backup values in won positions
rem sit lower than lc0's saturated means, so its gate never opened for us).
rem History: baseline 79.2%, C1 66.7%, C5 62.5% (all lc0, 24 games each).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set LOG=%REPO%\games\parity_armC.log
set STILLWATER_REFINE_MASK=0x3FF
set STILLWATER_LCB_K=0.3
set STILLWATER_PICK_K=0.5
set STILLWATER_FPU_RED=0.2
set STILLWATER_ML_THRESH=0.5

echo === ARM C (C6: 0x3FF b32 mlt0.5) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=Lc0-800 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci restart=off nodes=800 option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW-C6 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci restart=off nodes=768 option.RustCore=true option.Batch=32 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" -each tc=inf -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 12 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\parity_armC.pgn" >> "%LOG%" 2>&1
echo ARM C COMPLETE %DATE% %TIME% >> "%LOG%"
