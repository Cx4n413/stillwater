@echo off
rem Compiled-core validation: RustEngine (batch 256) vs SF UCI_Elo 3190,
rem 60+1, book openings, arbiter draw semantics. Baseline to beat: the
rem Python engine's 3-0-7 (65%) from the morning A/B.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\rs_match.log

echo === RS VALIDATION starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-rust cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.StrictDraws=true option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=sequential plies=10 -rounds 5 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\rs_match.pgn" >> "%LOG%" 2>&1
echo === RS VALIDATION COMPLETE %DATE% %TIME% === >> "%LOG%"
