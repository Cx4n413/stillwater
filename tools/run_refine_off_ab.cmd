@echo off
rem REGRESSION LOCALIZER: same build, Refine OFF (mask 0 = legacy pre-Refine
rem search) vs SF-3190L, identical conditions to the gauntlet's 3190 rung.
rem Compare to Refine ON = 2-13-25 = 36.2%. If OFF climbs to ~55-65%, the
rem Refine package regressed real-game play; if OFF is also ~36%, the cause
rem is the rust port/backend, not Refine. 30 games.
rem NOTE: STILLWATER_REFINE_MASK must NOT be set (it would override the option).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\refine_off_ab.log

echo === REFINE-OFF A/B starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-legacy cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=false option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 15 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\refine_off_ab.pgn" >> "%LOG%" 2>&1
echo === REFINE-OFF A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
