@echo off
rem ============================================================================
rem  #1 DISTRIBUTION-NATIVE RISK-UTILITY A/B (efficient + definite).
rem  Direct paired self-play: BASELINE (risk off, byte-identical robustpick) vs
rem  TREATMENT (risk-averse readout). Identical engines except the one readout.
rem  SPRT[elo0=0, elo1=12] alpha=beta=0.05: STOPS EARLY on a clear accept (>=+12)
rem  or reject (<=0), so we don't burn games once the answer is in. Paired
rem  openings + repeat for color balance; conc 1 (one GPU); StrictDraws for the
rem  cutechess arbiter; Harvest/Ledger off so the test can't pollute the corpus.
rem  timemargin absorbs the one-time DirectML warmup (restart=off -> paid once).
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BASE=%REPO%\stillwater_uci.bat
set TREAT=%REPO%\stillwater_risk.bat
set TB=%REPO%\nets\syzygy
set BOOK=%REPO%\games\gauntlet_book.pgn
set PGN=%REPO%\games\risk_ab.pgn
set LOG=%REPO%\games\risk_ab.log

echo === RISK A/B (averse vs baseline) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" ^
  -engine name=SW-base  cmd="%BASE%"  dir="%REPO%" proto=uci restart=off option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -engine name=SW-averse cmd="%TREAT%" dir="%REPO%" proto=uci restart=off option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" ^
  -each tc=40/120 timemargin=20000 ^
  -openings file="%BOOK%" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -sprt elo0=0 elo1=12 alpha=0.05 beta=0.05 ^
  -rounds 400 -games 2 -pgnout "%PGN%" >> "%LOG%" 2>&1
echo === RISK A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
