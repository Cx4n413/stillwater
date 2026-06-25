@echo off
rem ============================================================================
rem  #1 RISK-UTILITY strength test, REDESIGNED per adversarial review.
rem  Risk-AVERSE's claimed benefit (shrink the loss tail) is only observable
rem  where SW actually LOSES -> measure it vs a competitive STRONGER opponent,
rem  not in saturated peer self-play (which has no loss dynamic range).
rem  Two arms (SW-base, SW-averse) vs a fixed SF-3190L gauntlet seed; compare
rem  loss% and score. Higher decisive rate than self-play = far higher power.
rem  conc 1: SF runs on CPU, SW on GPU, one game at a time -> no contention.
rem  Game count is provisional -- size it from tools/scope_risk.py first.
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set BASE=%REPO%\stillwater_uci.bat
set TREAT=%REPO%\stillwater_risk.bat
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\risk_vs_sf.pgn
set LOG=%REPO%\games\risk_vs_sf.log

rem Opponent = SF18 NODE-LIMITED @192k (the calibrated ~3515 CCRL rung, ~83 Elo
rem above SW so SW loses enough to give the averse loss-reduction dynamic range).
rem SF is node-limited (tc=inf -> near-instant, strength-calibrated, contention-
rem immune); SW arms run a real clock @40/60 (faster -> more losses = more power
rem AND ~half the wall-clock; the readout effect is move-choice, ~TC-robust).
rem Both SW arms face the IDENTICAL SF, so base-vs-SF minus averse-vs-SF isolates
rem the readout. ~80 games/arm; extend if the loss% difference is borderline.
echo === RISK vs SF18-N192k (base + averse) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -tournament gauntlet ^
  -engine name=SF18-N192k cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false tc=inf nodes=192000 ^
  -engine name=SW-base   cmd="%BASE%"  dir="%REPO%" proto=uci restart=off tc=40/60 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -engine name=SW-averse cmd="%TREAT%" dir="%REPO%" proto=uci restart=off tc=40/60 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -each timemargin=20000 ^
  -openings file="%BOOK%" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -rounds 40 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === RISK vs SF COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
