@echo off
rem ============================================================================
rem  EVAL NET TEST -- BT4 vs t3 vs t1(fallback): does a faster/weaker net help?
rem ----------------------------------------------------------------------------
rem  HYPOTHESIS UNDER TEST: a faster net lets SW relax the lattice DEEPER per
rem  move. The engine's own prior finding (~2.3x evals ~= 0 self-play Elo) says
rem  depth is NOT the binding constraint -- eval QUALITY is. So we expect the
rem  faster/weaker nets to be ~neutral-to-negative. This test DECOUPLES the two
rem  variables: throughput (evals/s) vs tactical strength at a MATCHED budget.
rem
rem    THROUGHPUT  -> net_throughput.py: full-budget evals/s on a fixed middlegame
rem                  (root never proven -> no early stop -> clean evals/s).
rem    STRENGTH    -> tactical_bench.py: WAC-300 solve-rate at matched movetime,
rem                  REAL search (Court early-stop allowed -- deployed behavior).
rem                  Two budgets: 1000ms (~deployed per-move) and 300ms (short,
rem                  where the faster net's depth edge should matter MOST).
rem
rem  READ-OUT: if t1 (the ~2.7x net) holds/raises solve-rate vs BT4 at matched
rem  movetime -> depth converts, the swap is a real win -> chase a fast pipeline.
rem  If t1 DROPS -> BT4's eval quality is load-bearing -> do NOT chase speed,
rem  invest in eval QUALITY (Distillery retrain). Same search config every run;
rem  the ONLY variable is the .onnx. CPU+GPU -- run ONLY when the GPU is free.
rem ============================================================================
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set NB=%REPO%\nets\BT4-1024x15x32h-policytune.onnx
set N3=%REPO%\nets\t3-512x15x16h-distill.onnx
set N1=%REPO%\nets\fallback.onnx
set LOG=%REPO%\games\eval_nettest.log
cd /d "%REPO%"

echo === EVAL NET TEST start %DATE% %TIME% === > "%LOG%"
echo Nets: BT4(370MB) / t3(171MB) / t1-fallback(40MB). Same search cfg; only net varies. >> "%LOG%"

echo. >> "%LOG%"
echo --- THROUGHPUT (full-budget evals/s, 15s, middlegame) --- >> "%LOG%"
"%PYEXE%" -u tools\net_throughput.py "%NB%" 15 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\net_throughput.py "%N3%" 15 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\net_throughput.py "%N1%" 15 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- TACTICAL WAC-300 mt=1000 (deployed-ish per-move; real early-stop) --- >> "%LOG%"
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt "NetPath=%NB%" --tag bt4_mt1000 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt "NetPath=%N3%" --tag t3_mt1000 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt "NetPath=%N1%" --tag t1_mt1000 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- TACTICAL WAC-300 mt=300 (short budget; depth edge should matter most) --- >> "%LOG%"
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 300 --opt Refine=true --opt "NetPath=%NB%" --tag bt4_mt300 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 300 --opt Refine=true --opt "NetPath=%N3%" --tag t3_mt300 >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 300 --opt Refine=true --opt "NetPath=%N1%" --tag t1_mt300 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === EVAL NET TEST COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
