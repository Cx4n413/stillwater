@echo off
rem PARITY ARMS, iteration 1. Baseline (live 0xAB): 14-0-10 lc0 (79.2%).
rem Arm A: C1 = nofloor + count-LCB(.3) + robust pick(.5), batch 128.
rem Arm B: C5 = C1 + uflight + fpu(.2), batch 32 (deep serial PUCT).
rem Same protocol as the baseline: SW nodes=768, lc0 nodes=800, tc=inf.
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set LC0=C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe
set BT4=%REPO%\nets\BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz
set TB=%REPO%\nets\syzygy
set LOG=%REPO%\games\parity_arms.log
set STILLWATER_LCB_K=0.3
set STILLWATER_PICK_K=0.5
set STILLWATER_FPU_RED=0.2

echo === ARM A (C1 0x3BB b128) starting %DATE% %TIME% === > "%LOG%"
set STILLWATER_REFINE_MASK=0x3BB
"%CUTE%" -engine name=Lc0-800 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci restart=off nodes=800 option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW-C1 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci restart=off nodes=768 option.RustCore=true option.Batch=128 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" -each tc=inf -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 12 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\parity_armA.pgn" >> "%LOG%" 2>&1

echo === ARM B (C5 0x3FF b32) starting %DATE% %TIME% === >> "%LOG%"
set STILLWATER_REFINE_MASK=0x3FF
"%CUTE%" -engine name=Lc0-800 cmd="%LC0%" dir="C:\Users\nonna\Downloads\lc0\cuda12" proto=uci restart=off nodes=800 option.WeightsFile="%BT4%" option.SyzygyPath="%TB%" -engine name=SW-C5 cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci restart=off nodes=768 option.RustCore=true option.Batch=32 option.StrictDraws=true option.Harvest=false option.Ledger=false option.SyzygyPath="%TB%" -each tc=inf -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 -rounds 12 -games 2 -repeat -concurrency 1 -recover -pgnout "%REPO%\games\parity_armB.pgn" >> "%LOG%" 2>&1

echo PARITY ARMS COMPLETE %DATE% %TIME% >> "%LOG%"
