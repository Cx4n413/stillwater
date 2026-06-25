@echo off
rem THE EVAL-PARITY MATCH: Lc0 vs STILLWATER, same BT4 weights, fixed 800
rem nodes per move both sides. No time pressure (tc=inf), no ponder, conc 1
rem (mover owns the GPU), same syzygy TBs, paired random openings, 60 games.
rem restart=off keeps both engines resident (ucinewgame between games).
rem This isolates SEARCH QUALITY PER EVALUATION — the architecture question.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set LOG=%REPO%\games\parity_match.log

echo === PARITY MATCH starting %DATE% %TIME% === > "%LOG%"
rem SW gets nodes=768 vs lc0's 800: batch quantization makes SW's MEASURED
rem evals ~790 vs lc0's ~830 — the residual deficit runs AGAINST us, so a
rem >=50% result is airtight. Actual per-move counts audited from the PGN.
"%CUTE%" -engine name=Lc0-800 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci restart=off nodes=800 option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW-768 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci restart=off nodes=768 option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" -each tc=inf -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 30 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\parity_match.pgn" >> "%LOG%" 2>&1
echo PARITY MATCH COMPLETE %DATE% %TIME% >> "%LOG%"
