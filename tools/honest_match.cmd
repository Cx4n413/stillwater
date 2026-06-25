@echo off
rem ============================================================================
rem  HONEST-MAX vs PREVIOUS VERSION -- the A/B the user asked for.
rem  SW-honest = honest-max ON (tools\hk_arm.bat sets STILLWATER_HONEST_K);
rem  SW-base   = honest_k=0 == the PREVIOUS version, BIT-IDENTICAL (same binary,
rem  the if-honest_k>0 path is skipped). So this isolates the change exactly.
rem  Also runs STS-1000 honest vs base for a positional per-eval signal.
rem  200-game self-play, decisive openings + adjudication for power.
rem ============================================================================
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set LOG=%REPO%\games\honest_match.log
cd /d "%REPO%"
echo === HONEST-MAX A/B start %DATE% %TIME% === > "%LOG%"

rem --- positional per-eval signal (STS-1000): honest vs base (vs base 77.7) ---
for /f "tokens=2 delims==" %%H in ('findstr "STILLWATER_HONEST_K" tools\hk_arm.bat') do set HKVAL=%%H
echo --- STS-1000 honest_k=%HKVAL% --- >> "%LOG%"
set STILLWATER_HONEST_K=%HKVAL%
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --epd games\sts.epd --limit 1000 --opt Refine=true --tag hk_sts >> "%LOG%" 2>&1
set STILLWATER_HONEST_K=

echo --- MATCH SW-honest(k=%HKVAL%) vs SW-base(k=0) 200g 15+0.3 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SW-honest cmd="%REPO%\tools\hk_arm.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 ^
  -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 ^
  -each tc=15+0.3 timemargin=2000 ^
  -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%REPO%\games\honest_ab.pgn" -rounds 100 -games 2 >> "%LOG%" 2>&1

echo === HONEST-MAX A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
