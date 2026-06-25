@echo off
rem ARM D, iteration 3: C9 = C5 + R_COARSER50 (0xBFF) — lattice survives
rem long maneuvering (one r50 bucket below clock 64) instead of re-keying
rem every 16 plies. Targets the grind losses (11-21 eval sawteeth/game).
rem History: baseline 79.2%, C1 66.7%, C5 62.5%, C6 62.5% (lc0, 24g each).
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set LOG=%REPO%\games\parity_armD.log
set STILLWATER_REFINE_MASK=0xBFF
set STILLWATER_LCB_K=0.3
set STILLWATER_PICK_K=0.5
set STILLWATER_FPU_RED=0.2

echo === ARM D (C9: 0xBFF b32 coarse-r50) starting %DATE% %TIME% === > "%LOG%"
"%CUTE%" -engine name=Lc0-800 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci restart=off nodes=800 option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW-C9 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci restart=off nodes=768 option.RustCore=true option.Batch=32 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" -each tc=inf -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 12 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\parity_armD.pgn" >> "%LOG%" 2>&1
echo ARM D COMPLETE %DATE% %TIME% >> "%LOG%"
