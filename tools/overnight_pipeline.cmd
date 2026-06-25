@echo off
rem ============================================================================
rem  OVERNIGHT EVALUATOR-DISTILLATION PIPELINE (autonomous, detached)
rem ----------------------------------------------------------------------------
rem  STILLWATER is eval-bound and already on the strongest off-the-shelf net
rem  (BT4 SOTA). The ambitious lever tonight: distill a STRONGER evaluator
rem  (Stockfish, ~3600) into a correction on BT4's raw eval. SF-distill target =
rem  SF_wdl_value - BT4_raw; raw is the net's first impression (search-free), so
rem  no slow settled-harvest is needed -> a FAST raw pass frees the GPU for heavy
rem  validation. Also trains a (shallow) self-distill corrector for comparison.
rem    1 RAW HARVEST  15k diverse FENs @0.25s -> BT4 raw (+shallow settled)
rem    2 TRAIN        self-distill + SF-distill correctors (SF labels made in
rem                   parallel by tools/sf_label.py -> harvest/sf_labels.jsonl)
rem    3 TACTICAL     WAC-300 + STS-1000, Corrector OFF / self / SF (accuracy)
rem    4 MATCH        SW-SFcorr vs base (60g) and SW-selfcorr vs base (40g)
rem    5 done. Results in this log (=== markers). Nothing auto-deploys to the bot.
rem  The corrector.npz is SWAPPED (copy) before each arm since the engine loads
rem  one corrector.npz at startup.
rem ============================================================================
setlocal
set PYEXE=C:\Users\nonna\miniconda3\python.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set LOG=%REPO%\games\overnight_pipeline.log
cd /d "%REPO%"

echo === OVERNIGHT PIPELINE START %DATE% %TIME% === > "%LOG%"

echo. >> "%LOG%"
echo === PHASE 1: RAW HARVEST (15k FENs @0.25s) %DATE% %TIME% === >> "%LOG%"
"%PYEXE%" -u tools\harvest_positions.py games\harvest_fens_15k.txt 250 5000 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === PHASE 2: BUILD + TRAIN CORRECTORS %DATE% %TIME% === >> "%LOG%"
echo --- self-distill --- >> "%LOG%"
"%PYEXE%" -u tools\build_dataset.py --out dataset_self.npz >> "%LOG%" 2>&1
"%PYEXE%" -u tools\train_corrector.py --in dataset_self.npz --out "%REPO%\corrector_self.npz" --force >> "%LOG%" 2>&1
echo --- SF-distill (teacher = Stockfish) --- >> "%LOG%"
"%PYEXE%" -u tools\build_dataset.py --sf harvest\sf_labels.jsonl --out dataset_sf.npz >> "%LOG%" 2>&1
"%PYEXE%" -u tools\train_corrector.py --in dataset_sf.npz --out "%REPO%\corrector_sf.npz" --force >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === PHASE 3: TACTICAL/POSITIONAL A/B (OFF / self / SF) %DATE% %TIME% === >> "%LOG%"
echo --- base (Corrector OFF) --- >> "%LOG%"
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt Corrector=false --tag base_wac >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --epd games\sts.epd --limit 1000 --opt Refine=true --opt Corrector=false --tag base_sts >> "%LOG%" 2>&1
echo --- self-distill corrector --- >> "%LOG%"
copy /Y "%REPO%\corrector_self.npz" "%REPO%\corrector.npz" >nul
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt Corrector=true --tag self_wac >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --epd games\sts.epd --limit 1000 --opt Refine=true --opt Corrector=true --tag self_sts >> "%LOG%" 2>&1
echo --- SF-distill corrector --- >> "%LOG%"
copy /Y "%REPO%\corrector_sf.npz" "%REPO%\corrector.npz" >nul
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --opt Refine=true --opt Corrector=true --tag sf_wac >> "%LOG%" 2>&1
"%PYEXE%" -u tools\tactical_bench.py --engine sw --movetime 1000 --epd games\sts.epd --limit 1000 --opt Refine=true --opt Corrector=true --tag sf_sts >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === PHASE 4a: MATCH SW-SFcorr vs SW-base (60g, 15+0.3) %DATE% %TIME% === >> "%LOG%"
copy /Y "%REPO%\corrector_sf.npz" "%REPO%\corrector.npz" >nul
"%CUTE%" ^
  -engine name=SW-SFcorr cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 option.Corrector=true ^
  -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 option.Corrector=false ^
  -each tc=15+0.3 timemargin=2000 ^
  -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%REPO%\games\corrector_sf_ab.pgn" -rounds 30 -games 2 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === PHASE 4b: MATCH SW-selfcorr vs SW-base (40g, 15+0.3) %DATE% %TIME% === >> "%LOG%"
copy /Y "%REPO%\corrector_self.npz" "%REPO%\corrector.npz" >nul
"%CUTE%" ^
  -engine name=SW-selfcorr cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 option.Corrector=true ^
  -engine name=SW-base cmd="%PYEXE%" arg=-u arg=-m arg=stillwater.uci dir="%REPO%" proto=uci option.RustCore=true option.Batch=128 option.Refine=true option.StrictDraws=true option.DrawContempt=10 option.Corrector=false ^
  -each tc=15+0.3 timemargin=2000 ^
  -openings file="%REPO%\games\openings.pgn" format=pgn order=random plies=12 ^
  -repeat -recover -concurrency 1 ^
  -draw movenumber=80 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%REPO%\games\corrector_self_ab.pgn" -rounds 20 -games 2 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === OVERNIGHT PIPELINE COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
