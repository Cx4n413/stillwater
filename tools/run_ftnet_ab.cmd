@echo off
rem ============================================================================
rem  PILOT GAUNTLET: fine-tuned BT4 (cloud) vs baseline BT4.
rem  FIXED NODES (tc=inf nodes=800) -> speed-independent, so the fp32 ft-net vs
rem  fp16 baseline is a FAIR per-eval move-quality test. Both arms = deployed
rem  config; only NetPath differs. Baseline points at the ORIGINAL BT4 explicitly
rem  (auto-discovery would otherwise pick the newer ft-net for both). SPRT stops
rem  early. conc 1 (one GPU). Run on the local 5070 (bot paused).
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BAT=%REPO%\stillwater_uci.bat
set BASE_NET=%REPO%\nets\BT4-1024x15x32h-policytune.onnx
set FT_NET=%REPO%\nets\BT4_ft.onnx
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\ftnet_ab.pgn
set LOG=%REPO%\games\ftnet_ab.log

echo === FT-NET A/B (ft vs base, fixed 800 nodes) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-base cmd="%BAT%" dir="%REPO%" proto=uci restart=off tc=inf nodes=800 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%BASE_NET%" ^
  -engine name=SW-ft   cmd="%BAT%" dir="%REPO%" proto=uci restart=off tc=inf nodes=800 option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" option.NetPath="%FT_NET%" ^
  -openings file="%BOOK%" format=pgn order=random plies=12 -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -sprt elo0=-15 elo1=10 alpha=0.05 beta=0.05 ^
  -rounds 100 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === FT-NET A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
