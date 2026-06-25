@echo off
rem Quick time-management verification: 4 games at 60+1 vs SF-3190L after the
rem court.budgets extension-cap fix. Pass if zero time forfeits and the engine
rem spends sustainably in the opening (no 5s+ moves).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\time_verify.log

echo === TIME VERIFY starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-tuned cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=sequential plies=10 -rounds 2 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\time_verify.pgn" >> "%LOG%" 2>&1
echo === TIME VERIFY COMPLETE %DATE% %TIME% === >> "%LOG%"
