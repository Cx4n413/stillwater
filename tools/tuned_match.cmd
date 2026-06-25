@echo off
rem ============================================================================
rem  STS-TUNED CONSTANTS vs PREVIOUS VERSION (the missing game validation).
rem  SW-tuned = tools\tuned_arm.bat (the shelved tuned vector via env vars);
rem  SW-base  = default constants == the deployed/previous version, same binary.
rem  150-game self-play, decisive openings + adjudication. Ship the tuned vector
rem  to the bot only if it WINS here (the timed-game gate that was never run).
rem ============================================================================
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set LOG=%REPO%\games\tuned_match.log
cd /d "%REPO%"
echo === STS-TUNED A/B start %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-tuned cmd="%REPO%\tools\tuned_arm.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 ^
  -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 ^
  -each tc=15+0.3 timemargin=2000 ^
  -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%REPO%\games\tuned_ab.pgn" -rounds 75 -games 2 >> "%LOG%" 2>&1
echo === STS-TUNED A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
