@echo off
rem Mass Distillery data generation: fast self-play with harvesting ON.
rem 100 games at 15+0.3 ~= 4-6 hours, ~6-10k records. Run when the GPU is
rem otherwise idle (pause the lichess bot first). Repeat liberally; the
rem dataset builder dedups nothing - more games = more positions.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\selfplay_harvest.log

echo === SELFPLAY HARVEST starting %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-h1 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Harvest=true option.Ledger=true -engine name=SW-h2 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Harvest=true option.Ledger=true -each tc=15+0.3 -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 50 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\selfplay_harvest.pgn" >> "%LOG%" 2>&1
echo === SELFPLAY HARVEST COMPLETE %DATE% %TIME% === >> "%LOG%"
