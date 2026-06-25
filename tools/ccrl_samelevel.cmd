@echo off
rem ============================================================================
rem  CCRL 40/15 (1-CPU) PLACEMENT -- SAME-LEVEL DIRECT ANCHORING
rem ----------------------------------------------------------------------------
rem  WHY THIS EXISTS: the node-limited-SF18-ladder method FAILED (high-node SF18
rem  self-play SATURATES -> 100%% draws -> the slope from the weak rungs up to the
rem  SF18=3627 pin is unmeasurable). This harness sidesteps the slope entirely:
rem  it plays SW DIRECTLY against engines with KNOWN CCRL 40/15 1-CPU ratings
rem  that BRACKET SW's hypothesized ~3350. Decisive, informative games vs SW give
rem  SW its CCRL rating directly, with NO slope extrapolation.
rem
rem  THE POOL (classical / pre-NNUE Stockfish -- ONE nps profile, so ONE clock-
rem  normalization factor S derived from the SF10 bench normalizes ALL of them):
rem    SF DD 3210  <  SF7 3303  <  SF8 3362  <  [SW ~3350?]  <  SF9 3425  <  SF10 3447
rem  SF8 and SF9 are the tightest two-sided bracket -> spend the most games there.
rem
rem  HOW STRENGTH IS REPRODUCED ON THIS BOX (Ryzen 5 7600X, not a 4770k):
rem  CCRL calibrates its 40/15 clock on an i7-4770k using SF10 as the reference.
rem  Each anchor plays a NORMALIZED time control SWNORM_TC = 40/(900/S) seconds,
rem  where S = this_machine_SF10_nps / 4770k_SF10_nps. At that TC each classical
rem  anchor reproduces its 4770k-40/15 = published CCRL 1-CPU rating ON THIS BOX.
rem  SW plays its REAL deployed control tc=40/900 (40 moves / 15 min) -- that is
rem  the thing being rated.
rem
rem  >>>>> HUMAN STEP (the ONE thing this file does NOT finalize) <<<<<
rem  After the live A/B match frees the CPU, run on THIS machine:
rem        stockfish_10_x64_bmi2.exe   (then type:  bench 16 1 13  )
rem  read the 'Nodes/second' line, then:
rem        S    = that_nps / 2000000          (2.0 M = 4770k SF10 1-core nps est)
rem        base = round(900 / S)              (central S~2.0 -> base~450)
rem  and set SWNORM_TC below to   40/<base>   (central placeholder: 40/450).
rem  (Band: S=1.4 -> 40/643 ; S=2.8 -> 40/321.) If the SF10 bench here is far
rem  from ~4.0 M nps, re-derive base BEFORE committing match time.
rem  OPTIONAL residual-killer: also bench SF DD and SF8 1-2 s; if any version's
rem  nps differs from SF10 by >8%%, give THAT engine its own S/base.
rem
rem  REGIME NOTES (adversarial guards applied):
rem    * conc-1: the anchors are TIME-limited (not node-limited) so they ARE
rem      sensitive to CPU contention -> run ONE game at a time, no clock fudge.
rem    * restart=on for SW: belt-and-suspenders vs the ORT VRAM leak (run SW on
rem      onnxruntime-DIRECTML, NOT CUDA). A fresh SW process per game keeps its
rem      eval/move constant across the whole placement.
rem    * NO SyzygyPath on EITHER side (fairness: SW is TB-blind). This is the
rem      TB-BLIND CCRL-EQUIVALENT regime -> likely over-states SW ~10-20 Elo in
rem      5-6-man endgames; report with that caveat. (Alt: give BOTH sides 3-4-5
rem      Syzygy to hit true CCRL regime -- not done here for SW fairness.)
rem    * Conservative adjudication ONLY (-draw / -resign), NO -tb adjudication,
rem      so SW is never ruled lost in a position it might hold.
rem    * SW config = the DEPLOYED build EXACTLY: RustCore Batch=128 Refine
rem      StrictDraws DrawContempt=10 Harvest=false Ledger=false.
rem
rem  GAME BUDGET: -repeat color-reversed pairs (pentanomial CI in fit_elo.py).
rem  More games on the SF8/SF9 straddle, fewer on the far DD/SF10 rungs. Edit the
rem  -rounds per block to hit the target CI (task target ~+/-40 Elo => ~100-160
rem  paired games total across the bracket; the <=12 stop rule is overkill here).
rem ============================================================================
setlocal

set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set ANCH=C:\Users\nonna\Downloads\anchors
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\placement_samelevel.pgn
set LOG=%REPO%\games\placement_samelevel.log
set SWERR=%REPO%\games\placement_samelevel_sw.stderr

rem --- anchor binaries (classical / pre-NNUE Stockfish = one nps profile) ---
set SFDD=%ANCH%\stockfish_dd_x64_modern.exe
set SF7=%ANCH%\stockfish_7_x64_bmi2.exe
set SF8=%ANCH%\stockfish_8_x64_bmi2.exe
set SF9=%ANCH%\stockfish_9_x64_bmi2.exe
set SF10=%ANCH%\stockfish_10_x64_bmi2.exe

rem ====================================================================
rem  >>> HUMAN: set this after the SF10 bench (central placeholder 40/450) <<<
rem  SWNORM_TC = 40/(900/S) ;  base = round(900/S) ;  central S~2.0 -> 40/450
rem ====================================================================
set SWNORM_TC=40/450

echo === SAME-LEVEL PLACEMENT starting %DATE% %TIME% === > "%LOG%"
echo SW = tc=40/900 (real deployed config) ; anchors = tc=%SWNORM_TC% (normalized, S-locked) >> "%LOG%"
echo Pool ^& CCRL 1-CPU anchors: SF DD 3210 / SF7 3303 / SF8 3362 / SF9 3425 / SF10 3447 >> "%LOG%"
echo conc-1, -repeat color-reversed pairs, restart=on, NO SyzygyPath, conservative adjudication >> "%LOG%"
echo If SWNORM_TC is still the 40/450 placeholder, FINALIZE it from the SF10 bench first. >> "%LOG%"

"%CUTE%" -tournament gauntlet ^
  -engine name=STILLWATER cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
    stderr="%SWERR%" restart=on ^
    option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true ^
    option.DrawContempt=10 option.Harvest=false option.Ledger=false ^
    tc=40/900 ^
  -engine name=SF-DD   cmd="%SFDD%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%SWNORM_TC% ^
  -engine name=SF7     cmd="%SF7%"  proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%SWNORM_TC% ^
  -engine name=SF8     cmd="%SF8%"  proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%SWNORM_TC% ^
  -engine name=SF9     cmd="%SF9%"  proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%SWNORM_TC% ^
  -engine name=SF10    cmd="%SF10%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%SWNORM_TC% ^
  -each timemargin=2000 ^
  -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 ^
  -resign movecount=4 score=900 ^
  -pgnout "%PGN%" ^
  -rounds 20 -games 2 >> "%LOG%" 2>&1

echo === SAME-LEVEL PLACEMENT COMPLETE %DATE% %TIME% === >> "%LOG%"
echo NEXT: python tools\fit_elo.py games\placement_samelevel.pgn  (ANCHORS rekeyed to the 5 classical SF 1-CPU ratings; SW free). >> "%LOG%"
echo TIP: spend MORE rounds on the SF8/SF9 straddle and FEWER on SF-DD/SF10 -- copy the -engine block for the straddle into a 2nd cutechess call with a higher -rounds, or run a -tournament gauntlet with only SF8+SF9 listed. >> "%LOG%"

endlocal
