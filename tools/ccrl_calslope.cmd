@echo off
rem ============================================================================
rem  CALIBRATE Part A -- SF18 node->Elo SLOPE (the lever that maps the concentrate
rem  rungs to CCRL). SF18-vs-SF18 node-limited self-play in 2-doubling steps that
rem  BRIDGE the concentrate rungs (48k, 192k) up to N0 (~27M = SF18's CCRL 40/15
rem  1-CPU node budget, pinned to 3627). Node-limited play is hardware-independent
rem  and strength-immune to CPU contention, so concurrency 3 is safe here (no SW,
rem  no GPU). ~10 games/pair. Fit Elo/doubling from calibrate_slope.pgn, then:
rem    rung_CCRL = 3627 - (doublings below N0) * (measured Elo/doubling)
rem    SW_CCRL   = rung_CCRL + SW's measured margin vs that rung (+79 / -57).
rem  Part B (real-40/900 pin cross-check vs Caissa/Starzix) is DEFERRED -- the
rem  compressed-frame pin (SF18 1-CPU = 3627) is already web-confirmed.
rem ============================================================================
setlocal
set CUTE=C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe
set SF=C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe
set REPO=C:\Users\nonna\Downloads\ExperimentalChessEngine
set BOOK=%REPO%\games\openings.pgn
set PGN=%REPO%\games\calibrate_slope.pgn
set LOG=%REPO%\games\calibrate_slope.log

echo === CALIBRATE slope starting %DATE% %TIME% === > "%LOG%"

rem pairs (lo hi) in 2-doubling steps bridging 48k -> ~27M (N0)
for %%P in ("48000 192000" "192000 768000" "768000 3072000" "3072000 12288000" "12288000 27000000") do (
  for /f "tokens=1,2" %%a in (%%P) do (
    echo --- pair %%a vs %%b --- >> "%LOG%"
    "%CUTE%" ^
      -engine name=SF-%%a cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=%%a ^
      -engine name=SF-%%b cmd="%SF%" proto=uci option.Threads=1 option.Hash=256 option.Ponder=false option.MultiPV=1 tc=inf nodes=%%b ^
      -each timemargin=2000 -openings file="%BOOK%" format=pgn order=sequential plies=10 ^
      -repeat -recover -concurrency 3 ^
      -draw movenumber=60 movecount=8 score=8 -resign movecount=4 score=900 ^
      -pgnout "%PGN%" -rounds 5 -games 2 >> "%LOG%" 2>&1
  )
)
echo === CALIBRATE slope COMPLETE %DATE% %TIME% === >> "%LOG%"
endlocal
