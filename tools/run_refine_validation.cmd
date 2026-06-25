@echo off
rem REFINE VALIDATION, two phases run back-to-back on one GPU:
rem   Phase 1: H2H — Refine on vs off, same wheel, 16 games 60+1.
rem   Phase 2: vs SF-3190L — Refine arm, 20 games 60+1, sequential book
rem            (same instrument as the 50%/65%/55% historical baselines).
rem Harvest/Ledger OFF in both arms: no corpus pollution, no proof leakage.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\refine_validation.log

echo === PHASE 1 H2H refine-vs-legacy starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-refine cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SW-legacy cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=false option.StrictDraws=true option.Harvest=false option.Ledger=false -each tc=60+1 -openings file="%BOOK%" format=pgn order=random plies=12 -rounds 8 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\refine_h2h.pgn" >> "%LOG%" 2>&1

echo === PHASE 2 refine-vs-SF3190L starting %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-refine cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 10 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\refine_sf.pgn" >> "%LOG%" 2>&1

echo REFINE VALIDATION COMPLETE %DATE% %TIME% >> "%LOG%"
