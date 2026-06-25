@echo off
rem ============================================================================
rem  #90 strength A/B: max-backup-native value head vs baseline.
rem  Direct paired self-play (SW-vhead vs SW-base). #90 re-ranks moves broadly
rem  (not just in losing positions), so it changes many moves -> more decisive
rem  games -> self-play A/B has real power here. SPRT[elo0=0, elo1=8] stops early
rem  on a clear accept (head helps) or reject (no gain). Identical engines except
rem  the value head. conc 1 (one GPU). timemargin absorbs DML warmup.
rem  NOTE: vhead runs BT4-embed.onnx + a numpy MLP per batch -> slightly slower
rem  per eval; that is part of what the gauntlet measures (net effect on play).
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BASE=%REPO%\stillwater_uci.bat
set TREAT=%REPO%\stillwater_vhead.bat
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\vhead_ab.pgn
set LOG=%REPO%\games\vhead_ab.log

echo === VHEAD A/B (vhead vs baseline) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-base  cmd="%BASE%"  dir="%REPO%" proto=uci restart=off option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -engine name=SW-vhead cmd="%TREAT%" dir="%REPO%" proto=uci restart=off option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -each tc=40/60 timemargin=20000 ^
  -openings file="%BOOK%" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -sprt elo0=0 elo1=8 alpha=0.05 beta=0.05 ^
  -rounds 600 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === VHEAD A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
