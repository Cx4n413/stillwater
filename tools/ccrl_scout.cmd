@echo off
rem ============================================================================
rem  STAGE 3 of 4 -- CCRL 40/15 PLACEMENT : SCOUT
rem ----------------------------------------------------------------------------
rem  GOAL: bracket SW's level FAST so concentrate spends games only on the two
rem  flanking SF18 rungs that straddle SW's 50%. SW uses a SHORTER fixed-time
rem  control here purely to bracket cheaply -- this is NOT the final number.
rem
rem  WHAT IT RUNS: SW vs 3 SF18 node rungs straddling the expected SW level.
rem  Provisional rungs (compressed-frame placeholders; REFIT after calibrate's
rem  measured slope is known): nodes=24000 (~3050), 48000 (~3150), 95000 (~3250).
rem  18 games total = 6 per rung = 3 book lines x 2 colors.
rem
rem  SW TC: st=8 (8 s/move fixed) x the LOCKED concurrency-2 compensation factor
rem  from pre-flight. Placeholder uses st=9.2 (= 8 x 1.15). If pre-flight locked a
rem  different factor, set SWST = 8 x factor here. (st=N is fixed sec/move; it is
rem  mutually exclusive with tc=, so SW uses st= and the SF anchor uses tc=inf.)
rem
rem  PASS CRITERIA:
rem    * Identify the two ADJACENT rungs that bracket SW's 50% (one rung where
rem      SW scores >50%, one where SW scores <50%). If SW is OUTSIDE the 24k-95k
rem      span, extend by one rung in the indicated direction and add 6 games.
rem    * Monotonic staircase sanity: SW score DECREASES as SF nodes INCREASE.
rem      A non-monotone result flags noise / insufficient N / a rung error.
rem    * ZERO time forfeits. Any forfeit => fix SW time mgmt before concentrate.
rem
rem  FAIRNESS: NO SyzygyPath on either engine. Conservative adjudication only.
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\placement_scout.pgn
set LOG=%REPO%\games\placement_scout.log
set SWERR=%REPO%\games\placement_scout_sw.stderr

rem --- SW fixed sec/move for bracketing: 8s x 1.15 placeholder factor = 9.2s ---
rem --- Update SWST to 8 x <locked factor> if pre-flight re-derived it. ---
set SWST=9.2

echo === SCOUT starting %DATE% %TIME% === > "%LOG%"
echo SW = st=%SWST% s/move (8 x 1.15 placeholder), concurrency 2 >> "%LOG%"
echo SF rungs = nodes 24000 / 48000 / 95000 (provisional; refit after calibrate slope) >> "%LOG%"

echo --- rung 1/3: SF18 nodes=24000 (~3050 provisional) --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SW cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
    stderr="%SWERR%" ^
    option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true ^
    option.DrawContempt=10 option.Harvest=false option.Ledger=false ^
    st=%SWST% ^
  -engine name=SF18-N24k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=24000 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 3 -games 2 >> "%LOG%" 2>&1

echo --- rung 2/3: SF18 nodes=48000 (~3150 provisional) --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SW cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
    stderr="%SWERR%" ^
    option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true ^
    option.DrawContempt=10 option.Harvest=false option.Ledger=false ^
    st=%SWST% ^
  -engine name=SF18-N48k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=48000 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 3 -games 2 >> "%LOG%" 2>&1

echo --- rung 3/3: SF18 nodes=95000 (~3250 provisional) --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SW cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
    stderr="%SWERR%" ^
    option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true ^
    option.DrawContempt=10 option.Harvest=false option.Ledger=false ^
    st=%SWST% ^
  -engine name=SF18-N95k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=95000 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 3 -games 2 >> "%LOG%" 2>&1

echo === SCOUT COMPLETE %DATE% %TIME% === >> "%LOG%"
echo NEXT: identify the two adjacent rungs bracketing SW 50%%; verify monotonic staircase + zero forfeits; pass those two rungs to concentrate. >> "%LOG%"
endlocal
