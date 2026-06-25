@echo off
rem ANTI-DRIFT directional gauntlet (faster: tc=10+0.1 -> ~3-4k nodes/move on CUDA,
rem covers the bulk of the drift abandonment 768-4k). drift vs base, SAME net, only
rem the readout differs. SPRT + small cap for a ~4-6h directional read. Bot DOWN.
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set NET=%REPO%\nets\BT4-1024x15x32h-policytune.onnx
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\antidrift_dir.pgn
set LOG=%REPO%\games\antidrift_dir.log
echo === ANTI-DRIFT directional (drift d0.12 vs base, FIXED nodes=6000 tc=inf, CUDA) %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-base  cmd="%REPO%\sw_cuda_base.bat"  dir="%REPO%" proto=uci restart=off tc=inf nodes=6000 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%NET%" ^
  -engine name=SW-drift cmd="%REPO%\sw_cuda_drift.bat" dir="%REPO%" proto=uci restart=off tc=inf nodes=6000 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%NET%" ^
  -openings file="%BOOK%" format=pgn order=random plies=12 -repeat -recover -concurrency 1 ^
  -draw movenumber=40 movecount=8 score=20 -resign movecount=4 score=800 ^
  -sprt elo0=0 elo1=15 alpha=0.05 beta=0.05 ^
  -rounds 20 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
