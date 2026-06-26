@echo off
rem ANTI-DRIFT A/B -- CLEAN FIXED-NODES version. The tc=15+0.15 timed run flagged
rem rampantly (time forfeits dominated the score -> contaminated). Here every move
rem searches EXACTLY STILLWATER_FORCE_NODES nodes (clock ignored in uci.py), under a
rem generous tc the engine can never exhaust -> ZERO time losses, pure readout A/B.
rem FORCE_NODES + DRIFT_EFLOOR are set here and INHERITED by both engine bats.
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set NET=%REPO%\nets\BT4-1024x15x32h-policytune.onnx
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\antidrift_nodes.pgn
set LOG=%REPO%\games\antidrift_nodes.log
set STILLWATER_FORCE_NODES=3000
set STILLWATER_DRIFT_EFLOOR=1800
echo === ANTI-DRIFT A/B FIXED-NODES (drift vs base, %STILLWATER_FORCE_NODES% nodes/move, CUDA) %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-base  cmd="%REPO%\sw_cuda_base.bat"  dir="%REPO%" proto=uci tc=600+5 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%NET%" ^
  -engine name=SW-drift cmd="%REPO%\sw_cuda_drift.bat" dir="%REPO%" proto=uci tc=600+5 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%NET%" ^
  -openings file="%BOOK%" format=pgn order=random plies=12 -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -sprt elo0=0 elo1=15 alpha=0.05 beta=0.05 ^
  -rounds 20 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
