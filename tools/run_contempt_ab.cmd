@echo off
rem CONVERSION-FIX A/B vs SF-3190L on DirectML (leak-free), same conditions as
rem the 1-1-22 (50%, 92% draws) baseline. Both arms have Component B (proven-
rem mate min-distance pick, always on); they differ only in Component A's
rem DrawContempt. Arm 1 = treatment (10), Arm 2 = same-wheel control (0).
rem SHIP GATE: won-then-drawn rate drops / decisive% rises AND loss% does NOT
rem rise vs the control. Any loss increase = over-pressing -> revert.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\contempt_ab.log

echo === ARM C=10 (treatment) vs SF-3190L %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-c10 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false option.DrawContempt=10 -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 12 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\contempt_c10.pgn" >> "%LOG%" 2>&1

echo === ARM C=0 (control) vs SF-3190L %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-c0 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false option.DrawContempt=0 -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 12 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\contempt_c0.pgn" >> "%LOG%" 2>&1
echo === CONTEMPT A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
