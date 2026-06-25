@echo off
rem ============================================================================
rem  PIN THE RUNGS to CCRL via same-level anchors (reuses SW's 89 baseline games).
rem  SW is already +79 vs SF18@48k and -57 vs SF18@192k (placement_concentrate
rem  b1+v3). We need the CCRL value of those two node rungs. Play the NODE-LIMITED
rem  rungs (near-instant) vs the same-level CCRL-rated anchors at the SF10-
rem  normalized clock tc=40/480 (S~1.88 = 3.77M this-machine / 2.0M 4770k SF10).
rem  Rungs are node-limited (instant) so the anchors (time-limited) each get a
rem  dedicated core at concurrency 3 -> no contention, correct anchor timing,
rem  ~3x throughput. CPU-only (GPU free). Then:
rem    fit_elo over b1 + v3 + this pgn -> SW + rungs on the CCRL scale.
rem    sanity: SW = 48k_CCRL + 79  ==  192k_CCRL - 57  (cross-check).
rem  STRADDLES (from SW ~3320-3350): 48k ~3240 between SF-DD 3210 / SF7 3303;
rem  192k ~3380 between SF8 3362 / SF9 3425.
rem  NO SyzygyPath (fairness, matches SW's TB-blind baseline). Conservative adj.
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set ANCH=C:\Users\nonna\Downloads\anchors
set SF18=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\placement_pinrungs.pgn
set LOG=%REPO%\games\placement_pinrungs.log
set ATC=40/480

echo === PIN RUNGS starting %DATE% %TIME% (anchor tc=%ATC%, conc 3) === > "%LOG%"

rem --- 192k rung vs its straddle (SF8 3362 / SF9 3425) ---
echo --- SF18-N192k vs SF8 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N192k cmd="%SF18%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=192000 ^
  -engine name=SF8 cmd="%ANCH%\stockfish_8_x64_bmi2.exe" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%ATC% ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 3 -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 12 -games 2 >> "%LOG%" 2>&1

echo --- SF18-N192k vs SF9 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N192k cmd="%SF18%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=192000 ^
  -engine name=SF9 cmd="%ANCH%\stockfish_9_x64_bmi2.exe" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%ATC% ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 3 -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 12 -games 2 >> "%LOG%" 2>&1

rem --- 48k rung vs its straddle (SF-DD 3210 / SF7 3303) ---
echo --- SF18-N48k vs SF-DD --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N48k cmd="%SF18%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=48000 ^
  -engine name=SF-DD cmd="%ANCH%\stockfish_dd_x64_modern.exe" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%ATC% ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 3 -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 12 -games 2 >> "%LOG%" 2>&1

echo --- SF18-N48k vs SF7 --- >> "%LOG%"
"%CUTE%" ^
  -engine name=SF18-N48k cmd="%SF18%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=48000 ^
  -engine name=SF7 cmd="%ANCH%\stockfish_7_x64_bmi2.exe" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=%ATC% ^
  -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
  -repeat -recover -concurrency 3 -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
  -pgnout "%PGN%" -rounds 12 -games 2 >> "%LOG%" 2>&1

echo === PIN RUNGS COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
