@echo off
rem ============================================================================
rem SF LADDER GAUNTLET — measures the CURRENT engine (CUDA + Refine 0xBFF +
rem tuned constants) against Stockfish under the EXACT conditions of the
rem historical A/B tests, so the score is directly comparable to:
rem     BASE (features off) ............ 50%   (1-1-6)
rem     legacy rust .................... 55%   (1-0-9)
rem     Refine package (pre-tune) ...... 55%   (4-2-14)
rem     v0.2 python NEW ................ 65%   (3-0-7)   <- the bar to beat
rem
rem SF conditions held IDENTICAL to those runs: UCI_LimitStrength=true,
rem UCI_Elo=3190 (anchor) / 3100 (regression rung), tc=60+1, the same 10-opening
rem book (openings.pgn, sequential, plies=10), concurrency 1, no SF ponder.
rem SW side = the deployed engine config (RustCore, Batch 128, Refine, ponder,
rem StrictDraws for the cutechess arbiter); Harvest/Ledger OFF so games are
rem independent and the measurement is not inflated by cross-game memory —
rem matching the ledger-free historical arms. Tuned constants arrive via the
rem inherited STILLWATER_* environment (set by the launcher when tuning shipped).
rem 3190 runs FIRST: if the night runs out, the comparable anchor is still done.
rem ============================================================================
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\sf_gauntlet.log

echo === SF GAUNTLET starting %DATE% %TIME% === > "%LOG%"
echo tuned env: LCB=%STILLWATER_LCB_K% FPU=%STILLWATER_FPU_RED% MLT=%STILLWATER_ML_THRESH% CPI=%STILLWATER_CPUCT_INIT% CPF=%STILLWATER_CPUCT_FACTOR% CVAR=%STILLWATER_C_VAR% VLW=%STILLWATER_VLOSS_W% PICK=%STILLWATER_PICK_K% >> "%LOG%"

echo === RUNG 1: SF UCI_Elo=3190 (40 games, the comparable anchor) === >> "%LOG%"
"%CUTE%" -engine name=SW-tuned cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 20 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\sf_gauntlet_3190.pgn" >> "%LOG%" 2>&1

echo === RUNG 2: SF UCI_Elo=3100 (16 games, regression/saturation check) === >> "%LOG%"
"%CUTE%" -engine name=SW-tuned cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3100L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3100 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 8 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\sf_gauntlet_3100.pgn" >> "%LOG%" 2>&1

echo === SF GAUNTLET COMPLETE %DATE% %TIME% === >> "%LOG%"
