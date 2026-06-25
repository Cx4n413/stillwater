@echo off
rem ============================================================================
rem  STAGE 1 of 4 -- CCRL 40/15 PLACEMENT : PRE-FLIGHT
rem ----------------------------------------------------------------------------
rem  GOAL: lock the LIVE concurrency-2 compensation factor, confirm ZERO time
rem  forfeits by SW at the real 40/900 target clock, and sanity-check book/color
rem  balance BEFORE any long run. This replaces the synthetic single-position
rem  conc_bench 0.87 with a real-game measurement.
rem
rem  WHAT IT RUNS: SW (concurrency 2, clock x1.15 PLACEHOLDER compensation =>
rem  tc=40/1035) vs ONE mid SF18 node rung (nodes=120000, ~CCRL-3300 region)
rem  chosen so SW scores ~20-40% and games are decisive enough to expose any
rem  time trouble. 8 games = 4 book lines x 2 colors via -repeat.
rem
rem  PASS CRITERIA (evaluate from the log + pgn BEFORE proceeding to calibrate):
rem    [HARD GATE] ZERO time-forfeit losses by SW in any non-lost position.
rem        Any forfeit  =>  raise SW move-overhead / timemargin and RE-RUN.
rem        Do NOT proceed to later stages with a forfeit on record.
rem    [LOCK] Measure SW conc-2 evals-per-move (parse 'info ... nps' / node
rem        counts from the pgn move comments) vs the conc-1 single-game
rem        baseline. If conc-2 evals/move are within 3% of conc-1 AFTER the
rem        1.15x clock, the placeholder is good. If OUTSIDE 3%, RE-DERIVE
rem        factor = (conc-1 nps)/(conc-2 nps), edit tc=40/<900*factor> in the
rem        calibrate/scout/concentrate scripts, and lock that exact multiplier.
rem        If the factor varies across game phases by >5%, DROP to
rem        concurrency 1 for concentrate (rigor > speed; GPU is the bottleneck).
rem    [INFO] Book/color balance: all 4 lines played both colors; White-vs-Black
rem        score difference is informational only at N=8 (not a hard gate).
rem    [WATCHDOG] No SW UCI hang / ping-timeout: -recover restarts a crashed
rem        engine; any hang VOIDS that game (do not score it as a loss).
rem
rem  FAIRNESS: NO SyzygyPath on either engine (SW plays tablebase-blind, so the
rem  SF anchor must too). SW Harvest/Ledger OFF => games are independent, no
rem  cross-game memory inflation. Conservative adjudication only (no -tb).
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\placement_preflight.pgn
set LOG=%REPO%\games\placement_preflight.log
set SWERR=%REPO%\games\placement_preflight_sw.stderr

rem --- SW clock: 900s x 1.15 placeholder concurrency-2 compensation = 1035s ---
rem --- If pre-flight re-derives the factor, update SWTC here AND in the
rem --- calibrate/scout/concentrate scripts to tc=40/<900*factor>.
set SWTC=40/1035

echo === PRE-FLIGHT starting %DATE% %TIME% === > "%LOG%"
echo SW clock = tc=%SWTC% (40/900 x 1.15 placeholder), concurrency 2 >> "%LOG%"
echo SF anchor = nodes=120000 (~CCRL-3300), Threads=1 Hash=256, NO SyzygyPath >> "%LOG%"

"%CUTE%" ^
  -engine name=SW cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
    stderr="%SWERR%" ^
    option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true ^
    option.DrawContempt=10 option.Harvest=false option.Ledger=false ^
    tc=%SWTC% ^
  -engine name=SF18-N120k cmd="%SF%" proto=uci ^
    option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 ^
    tc=inf nodes=120000 ^
  -each timemargin=2000 ^
  -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 ^
  -resign movecount=4 score=900 ^
  -pgnout "%PGN%" ^
  -rounds 4 -games 2 >> "%LOG%" 2>&1

echo === PRE-FLIGHT COMPLETE %DATE% %TIME% === >> "%LOG%"
echo. >> "%LOG%"
echo NEXT: audit "%LOG%" + "%PGN%" against the PASS CRITERIA in the header. >> "%LOG%"
echo   - grep for any SW loss flagged 'on time' / 'forfeit' in a non-lost spot. >> "%LOG%"
echo   - run fit/eval-rate parse to compare conc-2 vs conc-1 evals-per-move. >> "%LOG%"
echo   - if factor != 1.15, edit SWTC in ALL stage scripts before continuing. >> "%LOG%"
endlocal
