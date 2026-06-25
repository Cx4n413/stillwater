@echo off
rem ANTI-DRIFT A/B: STILLWATER+anti-drift vs STILLWATER baseline, SAME net (BT4),
rem only the readout differs. CUDA venv (fast). tc=15+0.15 reaches ~5-6k nodes/move
rem -> exercises the drift regime (abandonment peaks 768-16k nodes). conc 1 (one
rem GPU). SPRT stops early; cap bounds the wall-clock. Run with the bot DOWN.
rem Sweep delta by setting STILLWATER_DRIFT_DELTA before calling (drift bat reads it).
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set NET=%REPO%\nets\BT4-1024x15x32h-policytune.onnx
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\antidrift_ab.pgn
set LOG=%REPO%\games\antidrift_ab.log
echo === ANTI-DRIFT A/B (drift vs base, tc 15+0.15, CUDA, delta %STILLWATER_DRIFT_DELTA%) %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-base  cmd="%REPO%\sw_cuda_base.bat"  dir="%REPO%" proto=uci restart=off tc=15+0.15 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%NET%" ^
  -engine name=SW-drift cmd="%REPO%\sw_cuda_drift.bat" dir="%REPO%" proto=uci restart=off tc=15+0.15 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%NET%" ^
  -openings file="%BOOK%" format=pgn order=random plies=12 -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -sprt elo0=0 elo1=15 alpha=0.05 beta=0.05 ^
  -rounds 70 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
