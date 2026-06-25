@echo off
rem DECISIVE PROOF: current engine (rust 0xBFF + safe budget) on DirectML — the
rem leak-free 65%-era backend — vs SF-3190L, same historical conditions. The
rem ONLY change from the 36% CUDA gauntlet is the backend (no GPU memory leak).
rem   recovers toward ~55-65%, no per-game decline, no stalls -> CUDA leak WAS
rem     the regression; DirectML is the fix.
rem   stays ~36% -> the leak is not the (sole) cause; keep hunting.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\dml_gauntlet.log

echo === DML GAUNTLET (rust 0xBFF, DirectML, safe budget) vs SF-3190L %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-dml cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 15 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\dml_gauntlet.pgn" >> "%LOG%" 2>&1
echo === DML GAUNTLET COMPLETE %DATE% %TIME% === >> "%LOG%"
