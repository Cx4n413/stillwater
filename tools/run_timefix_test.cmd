@echo off
rem TEST THE WORKFLOW'S FIX: current default engine (rust 0xBFF + CUDA) now with
rem the DECOUPLED time budget (opening-protected, middlegame-deep) vs SF-3190L,
rem same historical conditions. Compare to the 36% control.
rem   recovers toward ~55-65% -> depth/time WAS the cause + this is the fix.
rem   stays ~36% -> time refuted; run the python cleave next.
rem WATCH FOR TIME FORFEITS (the deeper budget could re-introduce flagging).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\timefix_test.log

echo === TIMEFIX TEST (rust 0xBFF + decoupled budget) vs SF-3190L %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-timefix cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 15 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\timefix_test.pgn" >> "%LOG%" 2>&1
echo === TIMEFIX TEST COMPLETE %DATE% %TIME% === >> "%LOG%"
