@echo off
rem Confirmation of the STS-tuned constants win (first run: +34.9 +/-23.2, LOS
rem 99.8%%, 150g). 200 fresh non-deterministic games (15+0.3 has timing jitter ->
rem different games even from the same openings). Combine tuned_ab.pgn +
rem tuned_confirm.pgn for the tight final estimate.
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set LOG=%REPO%\games\tuned_confirm.log
cd /d "%REPO%"
echo === STS-TUNED CONFIRM start %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-tuned cmd="%REPO%\tools\tuned_arm.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 ^
  -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 ^
  -each tc=15+0.3 timemargin=2000 ^
  -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%REPO%\games\tuned_confirm.pgn" -rounds 100 -games 2 >> "%LOG%" 2>&1
echo === STS-TUNED CONFIRM COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
