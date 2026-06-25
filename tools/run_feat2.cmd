@echo off
rem Proof-bursts + root-Thompson validation: features ON vs OFF, same wheel.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\feat2.log

echo === FEAT2 starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-feat cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Ledger=false option.Harvest=false option.ProofBursts=true option.RootThompson=true -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Ledger=false option.Harvest=false option.ProofBursts=false option.RootThompson=false -each tc=60+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=sequential plies=10 -rounds 8 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\feat2.pgn" >> "%LOG%" 2>&1
echo === FEAT2 COMPLETE %DATE% %TIME% === >> "%LOG%"
