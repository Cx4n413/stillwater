@echo off
rem ============================================================================
rem  FIX A/B -- does the rank-2 snap fix help? SW with the fix ENABLED
rem  (STILLWATER_MIN_SPEND=0.4 spend-the-bank + STILLWATER_VERIFY_DRAW=256
rem  draw-proof-stop, gated on path_cond from the rebuilt core) vs the SAME two
rem  rungs at the SAME config as the legacy baseline (conc-1, tc=40/900,
rem  gauntlet vs SF18-N48k & SF18-N192k). Compare the rung scores to the legacy
rem  baseline (SW +79 vs N48k / -57 vs N192k, from placement_concentrate_b1+v3).
rem  The new build is byte-identical at default, so this isolates the fix.
rem  FINER50/REPFORCE left OFF (test the core snap fix first). Fresh pgn.
rem ============================================================================
setlocal
set STILLWATER_MIN_SPEND=0.4
set STILLWATER_VERIFY_DRAW=256
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\placement_fix_ab.pgn
set LOG=%REPO%\games\placement_fix_ab.log
set SWERR=%REPO%\games\placement_fix_ab_sw.stderr

echo === FIX A/B (MIN_SPEND=0.4 VERIFY_DRAW=256) starting %DATE% %TIME% === >> "%LOG%"

"%CUTE%" -tournament gauntlet ^
  -engine name=SW-fix cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
    stderr="%SWERR%" ^
    option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true ^
    option.DrawContempt=10 option.Harvest=false option.Ledger=false ^
    tc=40/900 ^
  -engine name=SF18-N48k  cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=48000 ^
  -engine name=SF18-N192k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=192000 ^
  -each timemargin=2000 ^
  -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 ^
  -resign movecount=4 score=900 ^
  -pgnout "%PGN%" ^
  -rounds 60 -games 2 >> "%LOG%" 2>&1

echo === FIX A/B run ended %DATE% %TIME% === >> "%LOG%"
endlocal
