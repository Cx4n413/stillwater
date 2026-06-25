@echo off
rem ============================================================================
rem  CCRL 40/15 PLACEMENT : CONCENTRATE  (the measurement)
rem ----------------------------------------------------------------------------
rem  CONCURRENCY 1 -- the compensation factor was measured NON-UNIFORM across
rem  phases (middlegame 1.03x, endgame 1.25x; conc_factor.py), so concurrency-2
rem  cannot be cleanly compensated and would bias SW ~10-16 Elo low in endgames.
rem  conc-1 is ALSO the deployed config (the bot plays one game at a time on the
rem  one GPU), so this measures SW exactly as it really plays. Zero bias.
rem
rem  SW at the TRUE CCRL 40/15 control: tc=40/900 (40 moves / 900s, repeating,
rem  no increment), no compensation. GAUNTLET vs two SF18 node rungs that
rem  straddle SW (from pre-flight: SW ~44% vs SF18@120k, so 50% sits just below
rem  120k): SF18-N48k (SW ~ >50%) and SF18-N192k (SW ~ <50%) -- decisive flanks.
rem
rem  This runs ONE long gauntlet; cutechess writes each game to the pgn as it
rem  finishes. Fit the PARTIAL pgn periodically with tools/fit_elo.py and KILL
rem  this run when SW's bootstrap CI half-width reaches the target (~18 Elo ->
rem  reported ~+-20-25 with the systematic band; matches the +-20-30 goal).
rem  Discard any SW loss that is a clock forfeit in a non-lost position
rem  (pre-flight showed zero forfeits, so none expected).
rem
rem  FAIRNESS: NO SyzygyPath on either engine. Conservative adjudication only.
rem  SF anchors: Threads=1 Hash=256 Ponder=false MultiPV=1 (1-CPU frame).
rem  rung->CCRL mapping comes later from ccrl_calibrate.cmd (slope + SF18@N0=3627 pin).
rem ============================================================================
setlocal
rem LEGACY (deployed) config: STILLWATER_MIN_SPEND=0.0 = the engine as it runs
rem on lichess. This run measures the honest baseline placement; it pools with
rem the 15 pre-fix games (placement_concentrate_b1.pgn). The rank-1 spend-the-
rem bank fix stays in code, gated OFF here. (Rank-1 cut confidence-snaps 27->8%
rem but the dominant snaps are draw-proof/COARSER50 -> rank-2, deferred.)
set STILLWATER_MIN_SPEND=0.0
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\placement_concentrate_v3.pgn
set LOG=%REPO%\games\placement_concentrate_v3.log
set SWERR=%REPO%\games\placement_concentrate_v3_sw.stderr

echo === CONCENTRATE (conc-1, tc=40/900) starting %DATE% %TIME% === >> "%LOG%"
echo Gauntlet: SW vs SF18-N48k and SF18-N192k. Fit partial pgn, kill at CI target. >> "%LOG%"

"%CUTE%" -tournament gauntlet ^
  -engine name=SW cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ^
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
  -rounds 80 -games 2 >> "%LOG%" 2>&1

echo === CONCENTRATE run ended %DATE% %TIME% === >> "%LOG%"
endlocal
