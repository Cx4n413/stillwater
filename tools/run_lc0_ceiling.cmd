@echo off
rem ============================================================================
rem  ROUTE A: measure lc0+BT4's real strength on THIS box, anchored to SW=3432.
rem  lc0 full-strength (cuda12, NO node cap, real clock = uses its ~3x nps) vs
rem  STILLWATER deployed config (DirectML, tuned constants + convert + verify_draw
rem  + Refine 0xBFF + DrawContempt 10). concurrency 1 (mover owns the GPU).
rem    lc0_CCRL ~= 3432 + (H2H Elo diff).
rem  NOTE: 40/120 (~3s/move) is below the CCRL-40/15 regime; since SW is eval-bound
rem  (flat vs TC) and lc0 depth-converts (rises with TC), a fast-TC diff UNDERSTATES
rem  lc0's edge -> the resulting lc0 estimate is a CONSERVATIVE LOWER BOUND.
rem  timemargin=20000 absorbs SW's one-time DirectML warmup on move 1 (restart=off
rem  keeps both engines resident, so warmup is paid once for the whole match).
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set LC0DIR=C:\Users\nonna\Downloads\lc0\cuda12
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set SWBAT=%REPO%\stillwater_uci.bat
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\lc0_ceiling.pgn
set LOG=%REPO%\games\lc0_ceiling.log

echo === LC0 CEILING H2H starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=Lc0-BT4 cmd="%LC0%" dir="%LC0DIR%" proto=uci restart=off option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" ^
  -engine name=SW-deploy cmd="%SWBAT%" dir="%REPO%" proto=uci restart=off option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -each tc=40/120 timemargin=20000 ^
  -openings file="%BOOK%" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -rounds 25 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === LC0 CEILING H2H COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
