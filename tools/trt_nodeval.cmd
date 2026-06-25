@echo off
rem Throughput->move-quality proxy: WAC-300 at the DirectML-equiv (2000) vs
rem TRT-equiv (7600) node budget per move (~the node counts each backend reaches
rem at ~2s/move). If 7600 >> 2000, the extra search TRT buys converts to better
rem moves; if ~equal, the engine is eval-bound and throughput's value is faster
rem training-data generation (#1), not direct strength. TRT EP = leak-free.
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set STILLWATER_TRT=1
set LOG=%REPO%\games\trt_nodeval.log
cd /d "%REPO%"
echo === TRT NODE-A/B start %DATE% %TIME% === > "%LOG%"
"%PYEXE%" -u tools\tactical_bench.py --engine sw --nodes 2000 --opt Refine=true --tag n2000 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --nodes 7600 --opt Refine=true --tag n7600 >> "%LOG%" 2>&1
echo === TRT NODE-A/B COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
