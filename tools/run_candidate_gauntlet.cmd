@echo off
rem Strength-snapshot / non-regression gauntlet for the CANDIDATE package
rem (TRT + tuned + DrawContempt + policy-tiebreak), vs SF UCI_Elo=3190 at 60+1,
rem same 10-opening book, conc 1 -- directly comparable to the historical bar
rem (v0.2 NEW 65%, Refine 55%, base 50%). SW engine launched via the single-
rem command candidate bat (no python -m arg string for cutechess to mis-parse).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\candidate_gauntlet.log

echo === CANDIDATE GAUNTLET starting %DATE% %TIME% === > "%LOG%"
echo === SF UCI_Elo=3190 (40 games) === >> "%LOG%"
"%CUTE%" -engine name=SW-cand cmd="%REPO%\stillwater_candidate.bat" dir="%REPO%" proto=uci ponder option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 20 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\candidate_gauntlet.pgn" >> "%LOG%" 2>&1
echo === CANDIDATE GAUNTLET COMPLETE %DATE% %TIME% === >> "%LOG%"
