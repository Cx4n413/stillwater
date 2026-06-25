@echo off
rem CONVERSION-FIX A/B on TODAY's stack (shipped tuned constants via the bats,
rem NOT default constants like the old run_contempt_ab.cmd). Two arms each vs
rem SF-3190L, DirectML (leak-free, no TRT stall), 60+1, paired openings. They
rem differ ONLY in DrawContempt (0.10 treatment vs 0.0 control). Both have
rem Component B (proven-mate pick, always on). Primary endpoint = decisive /
rem conversion rate (won-then-drawn), NOT the raw Elo point estimate.
rem SHIP GATE: c10 score% >= c0 AND c10 losses <= c0 AND decisive%/conversion up.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\contempt_ab2.log

echo === ARM C=10 (treatment, tuned stack) vs SF-3190L %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-c10 cmd="%REPO%\stillwater_c10.bat" dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 25 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\contempt2_c10.pgn" >> "%LOG%" 2>&1

echo === ARM C=0 (control, tuned stack) vs SF-3190L %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-c0 cmd="%REPO%\stillwater_c0.bat" dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 25 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\contempt2_c0.pgn" >> "%LOG%" 2>&1
echo === CONTEMPT A/B2 COMPLETE %DATE% %TIME% === >> "%LOG%"
