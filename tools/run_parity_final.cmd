@echo off
rem FINAL CONFIRMATION ARM: C9 locked (0xBFF b32 lcb.3 fpu.2 pick.5),
rem 48 games for a tight CI. Campaign: 79.2% -> 66.7% -> 62.5% -> 60.4%.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set LOG=%REPO%\games\parity_final.log
set STILLWATER_REFINE_MASK=0xBFF
set STILLWATER_LCB_K=0.3
set STILLWATER_PICK_K=0.5
set STILLWATER_FPU_RED=0.2

echo === FINAL ARM (C9, 48 games) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=Lc0-800 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci restart=off nodes=800 option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW-final cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci restart=off nodes=768 option.RustCore=true option.Batch=32 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" -each tc=inf -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 24 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\parity_final.pgn" >> "%LOG%" 2>&1
echo FINAL ARM COMPLETE %DATE% %TIME% >> "%LOG%"
