@echo off
rem DECISIVE CLEAVE: current PYTHON engine (RustCore=false) vs SF-3190L, same
rem historical conditions as the 65% run and the 36% gauntlet. Encoders are
rem proven bit-identical, so this isolates rust-port (search/decode) vs shared
rem changes (time budget / throughput guard / CUDA backend).
rem   python ~65% -> regression is the RUST PORT.
rem   python ~36% -> regression is a SHARED change, rust exonerated.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\python_vs_sf.log

echo === PYTHON vs SF-3190L starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-python cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=false option.Batch=128 option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 15 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\python_vs_sf.pgn" >> "%LOG%" 2>&1
echo === PYTHON vs SF-3190L COMPLETE %DATE% %TIME% === >> "%LOG%"
