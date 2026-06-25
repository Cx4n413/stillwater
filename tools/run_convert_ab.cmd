@echo off
rem CONVERSION-FIX A/B: convert ON (Syzygy DTZ + endgame progress readout) vs
rem convert OFF, head-to-head on the SHIPPED tuned stack (DrawContempt=10,
rem DirectML, Refine). Same engine both sides except STILLWATER_CONVERT.
rem Endpoint: ON score% >= 50 (converts won endgames OFF shuffles into 3-folds)
rem AND no regression (OFF does NOT outscore ON). Conversion rate (won-then-
rem decisive vs won-then-drawn) read from the pgn is the primary signal.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\gauntlet_book.pgn
set LOG=%REPO%\games\convert_ab.log
echo === CONVERT A/B  ON vs OFF  %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-convON cmd="%REPO%\stillwater_conv_on.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.Harvest=false option.Ledger=false -engine name=SW-convOFF cmd="%REPO%\stillwater_uci.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.Harvest=false option.Ledger=false -each tc=15+0.2 -openings file="%BOOK%" format=pgn order=random plies=8 -rounds 20 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\convert_ab.pgn" >> "%LOG%" 2>&1
echo === CONVERT A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
