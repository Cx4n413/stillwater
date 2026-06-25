@echo off
rem Lens arm: ALL features on (ponder + syzygy 3-4-5 + opponent model + Lens +
rem conversion-time investment). Concurrency 1 because pondering keeps our GPU
rem busy on opponent time - same conditions as arm NEW for comparability.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LOG=%REPO%\games\feature_ab.log

echo === ARM LENS starting %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=SW-lens cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci ponder option.OpponentModel=true option.Lens=true option.StrictDraws=true -engine name=SF-3190L cmd="%SF%" proto=uci option.UCI_LimitStrength=true option.UCI_Elo=3190 -each tc=60+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=sequential plies=10 -rounds 5 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\feature_ab_lens.pgn" >> "%LOG%" 2>&1
echo === AB COMPLETE %DATE% %TIME% === >> "%LOG%"
