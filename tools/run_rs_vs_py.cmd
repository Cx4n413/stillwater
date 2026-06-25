@echo off
rem Head-to-head: compiled core vs Python engine. Same clock, NO ponder (the
rem mover gets the whole GPU - fair), arbiter draws, persistence off in both.
rem This directly measures what 3.4x evals/s is worth per move.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\rs_vs_py.log

echo === RS vs PY starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-rust cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Ledger=false option.Harvest=false -engine name=SW-python cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=false option.StrictDraws=true option.Ledger=false option.Harvest=false -each tc=60+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=sequential plies=10 -rounds 8 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\rs_vs_py.pgn" >> "%LOG%" 2>&1
echo === RS vs PY COMPLETE %DATE% %TIME% === >> "%LOG%"
