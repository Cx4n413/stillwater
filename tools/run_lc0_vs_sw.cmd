@echo off
rem THE GAP INSTRUMENT: Lc0 (same BT4 net, its own search+backend) vs STILLWATER.
rem Both get the same syzygy TBs. Conc 1 = each game owns the GPU. 60+1 standard.
rem StrictDraws=true on SW (cutechess arbiter semantics). No ponder either side.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set LOG=%REPO%\games\lc0_vs_sw.log

echo === LC0 vs SW starting %DATE% %TIME% === >> "%LOG%"
"%CUTE%" -engine name=Lc0-BT4 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.StrictDraws=true option.Harvest=false option.Ledger=true -each tc=60+1 -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 8 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\lc0_vs_sw.pgn" >> "%LOG%" 2>&1
echo === LC0 vs SW COMPLETE %DATE% %TIME% === >> "%LOG%"
