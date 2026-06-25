@echo off
rem ============================================================================
rem  STAGE 2 of 4 -- CCRL 40/15 PLACEMENT : CALIBRATE
rem ----------------------------------------------------------------------------
rem  GOAL: (A) measure the SF18 node->Elo SLOPE inline (authoritative, replaces
rem  the 50 Elo/doubling guess) and (B) validate the absolute N0 pin: SF18 at the
rem  solved N0 must reproduce the KNOWN CCRL gaps to Caissa 1.23 and Starzix 6.0.
rem
rem  --------------------------------------------------------------------------
rem  PART A  -- INLINE SLOPE (SF18 vs SF18, node-limited self-play)
rem  --------------------------------------------------------------------------
rem  Adjacent node rungs spanning the SW region up to ~N0. Each pair is a
rem  separate 2-engine match (clean pairwise Elo). tc=inf nodes=N both sides,
rem  Threads=1 Hash=256, NO SyzygyPath. ~16 games/pair (8 lines x 2 colors).
rem  Fit Elo/doubling from these in fit_elo.py -> the measured slope.
rem  Provisional rungs (refit after slope known): 24k,95k,380k,1.6M.
rem
rem  --------------------------------------------------------------------------
rem  PART B  -- PIN CROSS-CHECK (SF18@N0 vs Caissa 1.23 and Starzix 6.0)
rem  --------------------------------------------------------------------------
rem  All three at REAL 40/900 wall-clock, Threads=1, NO SyzygyPath (cleanest:
rem  same regime as SW's concentrate run, removes node<->clock transfer risk).
rem  SF18 here is FULL-STRENGTH timed (NOT node-limited) so the implied gaps are
rem  pure wall-clock CCRL-comparable. 20 games each pairing (10 lines x 2 colors).
rem
rem  PASS CRITERIA:
rem    * The inline slope is stable rung-to-rung (within ~+/-5 Elo/doubling) and
rem      lands in 40-60/doubling. If <35 or >70 => investigate Threads leakage or
rem      node overshoot BEFORE trusting the curve.
rem    * SF18 minus Caissa and SF18 minus Starzix reproduce the chosen CCRL frame
rem      gaps within ~1 sigma of the anchors' error bars. The measured gaps MUST
rem      land on ONE consistent frame. If neither, REJECT the pin: sweep N0
rem      +/-10/20% and pick the value that lands SF18 on its own CCRL rating.
rem    * SOLVE-FOR-N0: choose N0 so SF18@N0 == SF18's CCRL 40/15 1CPU rating AND
rem      the Caissa/Starzix gaps reproduce; report the +/-10% N0 sensitivity as a
rem      systematic band on SW's final number.
rem
rem  NOTE ON SCALE (verified 2026-06-13, FLAG): the live CCRL 40/15 1CPU list has
rem  been re-anchored UPWARD vs the project spec's compressed frame
rem  (SF18 3653 / Caissa 3623 / Starzix 3607). Current 1CPU figures seen:
rem  SF18 ~4103, Caissa 1.23 ~4021 (the SF18-Caissa gap ~+82 is PRESERVED and
rem  matches the spec's 'wide frame'). Set ANCHOR_* below to the values you pin
rem  the fit to, and key fit_elo.py ANCHORS to the EXACT names used here.
rem  RE-VERIFY the three absolute numbers on the live list before final reporting.
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set CAISSA=C:\Users\nonna\Downloads\anchors\caissa-1.23-x64-avx2.exe
set STARZIX=C:\Users\nonna\Downloads\anchors\Starzix-6.0-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set SLOPEPGN=%REPO%\games\calibrate_slope.pgn
set PINPGN=%REPO%\games\calibrate_pin.pgn
set LOG=%REPO%\games\calibrate.log

rem --- N0 PROVISIONAL: 27,000,000 nodes/move (4770k 1.20M nps x 22.5 eff s/move).
rem --- RESOLVE after PART A slope: set N0 so SF18@N0 == SF18 CCRL 1CPU rating.
set N0=27000000

echo === CALIBRATE starting %DATE% %TIME% === > "%LOG%"

rem ============================ PART A: SLOPE ================================
echo. >> "%LOG%"
echo === PART A: INLINE SF18-vs-SF18 SLOPE (node-limited self-play) === >> "%LOG%"

echo --- pair 1/4: 24000 vs 95000 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N24k  cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=24000 ^
  -engine name=SF18-N95k  cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=95000 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%SLOPEPGN%" -rounds 8 -games 2 >> "%LOG%" 2>&1

echo --- pair 2/4: 95000 vs 380000 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N95k  cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=95000 ^
  -engine name=SF18-N380k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=380000 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%SLOPEPGN%" -rounds 8 -games 2 >> "%LOG%" 2>&1

echo --- pair 3/4: 380000 vs 1600000 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N380k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=380000 ^
  -engine name=SF18-N1_6M cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=1600000 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%SLOPEPGN%" -rounds 8 -games 2 >> "%LOG%" 2>&1

echo --- pair 4/4: 1600000 vs N0 (=%N0%, the pin rung) --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N1_6M cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=1600000 ^
  -engine name=SF18-N0    cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=%N0% ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%SLOPEPGN%" -rounds 8 -games 2 >> "%LOG%" 2>&1

rem ============================ PART B: PIN ==================================
echo. >> "%LOG%"
echo === PART B: PIN CROSS-CHECK (real 40/900 wall-clock, Threads=1, NO TB) === >> "%LOG%"
echo SF18-N0 here = FULL-STRENGTH TIMED at 40/900 (NOT node-limited) so gaps are wall-clock CCRL-comparable. >> "%LOG%"

echo --- B1: SF18(40/900) vs Caissa 1.23(40/900) --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-40_900  cmd="%SF%"     proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=40/900 ^
  -engine name=Caissa-1.23   cmd="%CAISSA%" proto=uci option.Threads=1 option.Hash=256 tc=40/900 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PINPGN%" -rounds 10 -games 2 >> "%LOG%" 2>&1

echo --- B2: SF18(40/900) vs Starzix 6.0(40/900) --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-40_900  cmd="%SF%"      proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=40/900 ^
  -engine name=Starzix-6.0   cmd="%STARZIX%" proto=uci option.Threads=1 option.Hash=256 tc=40/900 ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 2 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PINPGN%" -rounds 10 -games 2 >> "%LOG%" 2>&1

echo === CALIBRATE COMPLETE %DATE% %TIME% === >> "%LOG%"
echo NEXT: fit the slope from calibrate_slope.pgn; solve N0 from calibrate_pin.pgn gaps vs the live CCRL 1CPU ratings; then refit scout/concentrate rungs. >> "%LOG%"
endlocal
