@echo off
rem Speed-optimized Distillery harvest: concurrency 2 at 10+1.
rem Two concurrent games halve each engine's GPU share (~750 evals/s), but the
rem 1s increment restores ~750 evals/move - the SAME label quality as the stock
rem 15+0.3 conc-1 run at ~2x the game throughput. 100 games ~= 2.5-3.5 hours.
rem Memory rule: conc 2 + >=1s increment is the parallelism ceiling on this box;
rem conc 3 recreates starvation. Pause the lichess bot first.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\selfplay_harvest_fast.log

echo === FAST HARVEST starting %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-h1 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Harvest=true option.Ledger=true -engine name=SW-h2 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Harvest=true option.Ledger=true -each tc=10+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 50 -games 2 -repeat -concurrency 2 -recover -pgnout "%REPO%\games\selfplay_harvest_fast.pgn" >> "%LOG%" 2>&1
echo === FAST HARVEST COMPLETE %DATE% %TIME% === >> "%LOG%"
