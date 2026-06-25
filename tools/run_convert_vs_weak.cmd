@echo off
rem CONVERSION-FIX gauntlet vs a WEAKER opponent (the real lichess scenario:
rem STILLWATER crushes, reaches won endgames, must convert). Two arms vs
rem SF-2600, DirectML, same tuned stack + DrawContempt=10; differ ONLY in
rem STILLWATER_CONVERT. Endpoint: convON wins% > convOFF wins% and convON
rem draws% < convOFF draws% (won endgames converted instead of 3-folded).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\gauntlet_book.pgn
set LOG=%REPO%\games\convert_weak.log
echo === ARM ON  (convert) vs SF-2600  %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-convON cmd="%REPO%\stillwater_conv_on.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.Harvest=false option.Ledger=false -engine name=SF-2600 cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=2600 -each tc=15+0.2 -openings file="%BOOK%" format=pgn order=sequential plies=8 -rounds 15 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\convert_weak_on.pgn" >> "%LOG%" 2>&1
echo === ARM OFF (control) vs SF-2600  %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-convOFF cmd="%REPO%\stillwater_uci.bat" dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.DrawContempt=10 option.Harvest=false option.Ledger=false -engine name=SF-2600 cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=2600 -each tc=15+0.2 -openings file="%BOOK%" format=pgn order=sequential plies=8 -rounds 15 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\convert_weak_off.pgn" >> "%LOG%" 2>&1
echo === CONVERT-vs-WEAK COMPLETE %DATE% %TIME% === >> "%LOG%"
