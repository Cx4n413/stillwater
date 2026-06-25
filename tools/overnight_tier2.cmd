@echo off
rem ============================================================================
rem  TIER-2 VALIDATION: nonlinear value recalibration (SF-distilled) vs base.
rem  Tests whether the +24%%-MAE nonlinear recal curve (recal_lut.npz), applied
rem  in the oracle via STILLWATER_RECAL=1, helps PLAY -- the linear corrector was
rem  +7.2%% MAE but ~ -23 Elo (MAE != Elo; value recal can detune the search).
rem  Both arms Corrector=false so this isolates the recalibration.
rem    tactical: WAC-300 + STS-1000 recal=ON  (compare to base WAC 90.7 / STS 77.7)
rem    match:    SW-recal (recal_on.bat) vs SW-base, 240 games 15+0.3 (~+/-21 Elo)
rem  Nothing auto-deploys; ship only on a clear in-play win.
rem ============================================================================
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set LOG=%REPO%\games\overnight_tier2.log
cd /d "%REPO%"

echo === TIER2 VALIDATION START %DATE% %TIME% === > "%LOG%"

echo. >> "%LOG%"
echo === TACTICAL recal=ON (vs base WAC 90.7 / STS 77.7) %DATE% %TIME% === >> "%LOG%"
set STILLWATER_RECAL=1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt Corrector=false --tag recal_wac >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --epd games\sts.epd --limit 1000 --opt Refine=true --opt Corrector=false --tag recal_sts >> "%LOG%" 2>&1
set STILLWATER_RECAL=

echo. >> "%LOG%"
echo === MATCH SW-recal vs SW-base (240g, 15+0.3) %DATE% %TIME% === >> "%LOG%"
"%CUTE%" ^
  -engine name=SW-recal cmd="%REPO%\tools\recal_on.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 option.Corrector=false ^
  -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 option.Corrector=false ^
  -each tc=15+0.3 timemargin=2000 ^
  -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%REPO%\games\recal_ab.pgn" -rounds 120 -games 2 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === TIER2 VALIDATION COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
