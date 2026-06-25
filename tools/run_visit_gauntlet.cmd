@echo off
rem STRUCTURE-LEVER A/B: visit-readout (band 0.15) vs baseline, direct paired
rem self-play, DirectML (TRT cold-load stalls cutechess), 60+1, the validated
rem 10-opening book played both colors. Only the final move-readout differs
rem between the two arms. The score of VisON vs VisOFF is the readout's Elo.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\visit_gauntlet.log

echo === VISIT-READOUT A/B starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=VisON cmd="%REPO%\stillwater_vison.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -engine name=VisOFF cmd="%REPO%\stillwater_visoff.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.Harvest=false option.Ledger=false -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 60 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\visit_gauntlet.pgn" >> "%LOG%" 2>&1
echo === VISIT-READOUT A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
