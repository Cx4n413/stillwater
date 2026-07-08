@echo off
rem ============================================================================
rem  RE-PLACEMENT after the 2026-07-07 fix package: SW (CUDA + court fixes +
rem  bank-spend + Aquifer) vs the SF10 anchor (CCRL 3447) at 40/120, the same
rem  protocol that placed the old deployment at 3432.
rem    SW_CCRL ~= 3447 + H2H Elo diff.
rem  Anchor options identical to the original ladder (1 thread, Hash 256).
rem  concurrency 1 (SW owns the GPU); timemargin absorbs CUDA warmup on move 1
rem  (restart=off keeps both engines resident).  Run with the BOT DOWN.
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set ANCH=C:\Users\nonna\Downloads\anchors
set TB=%REPO%\nets\syzygy
set SWBAT=%REPO%\stillwater_uci_cuda.bat
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\replacement_sf10.pgn
set LOG=%REPO%\games\replacement_sf10.log

echo === RE-PLACEMENT vs SF10 (3447) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SF10 cmd="%ANCH%\stockfish_10_x64_bmi2.exe" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 ^
  -engine name=SW-fixed cmd="%SWBAT%" dir="%REPO%" proto=uci restart=off option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -each tc=40/120 timemargin=20000 ^
  -openings file="%BOOK%" format=pgn order=random plies=12 -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -rounds 25 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
