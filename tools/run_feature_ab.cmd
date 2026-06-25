@echo off
rem A/B measurement: NEW (ponder + syzygy + opponent model) vs BASE (all off),
rem each vs Stockfish UCI_Elo 3190 at 60+1, 10 games, concurrency 1.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set LOG=%REPO%\games\feature_ab.log

echo === ARM NEW starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=SW-new cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.OpponentModel=true option.StrictDraws=true -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 5 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\feature_ab_new.pgn" >> "%LOG%" 2>&1

echo === ARM BASE starting %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.OpponentModel=false option.SyzygyPath=none option.StrictDraws=true -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%BOOK%" format=pgn order=sequential plies=10 -rounds 5 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\feature_ab_base.pgn" >> "%LOG%" 2>&1

echo === AB COMPLETE %DATE% %TIME% === >> "%LOG%"
