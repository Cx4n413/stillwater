@echo off
rem STILLWATER UCI launcher for GUI hosts (lichess-bot, cutechess, Arena...).
rem -u: unbuffered stdout so UCI replies are never stuck in a pipe buffer.
rem TUNED CONSTANTS -- VALIDATED +34.9 +/- 23.2 Elo (LOS 99.8%, 150g self-play
rem vs default constants, 2026-06-15). The STS-tuned vector: the engine plays
rem stronger with LESS search-pessimism (lcb_k 0.3->0, the opposite of the failed
rem honest-max experiment). Remove these set lines to revert to the old behavior.
rem CONVERSION FIX (validated 2026-06-18): Syzygy DTZ-optimal play in <=5-man
rem TB wins + an endgame king-drive/progress readout, so dead-won endgames are
rem CONVERTED instead of shuffled into a 3-fold (the bug that drew dozens of
rem live games up a queen/rook). Readout-level: no extra GPU/latency. Play-out
rem turned 3 real drawn-won games into mates; 40-game self-play A/B showed no
rem regression (3-3-34) and zero clean won-games thrown. STILLWATER_CONVERT=0
rem to disable.
set STILLWATER_CONVERT=1
rem VERIFY_DRAW (2026-06-18): re-validate a PATH-CONDITIONAL draw proof with this
rem many fresh court-directed evals before snapping it -- stops SW from instantly
rem accepting a repetition "draw" its own descent assumed (the documented loss/
rem premature-draw class) when the position may actually be winnable. Bounded by
rem VERIFY_DRAW_FRAC*soft (0.25) so it can NEVER drain the clock -> no flag risk;
rem unconditional draws (insufficient material, 50-move, stalemate, dead TB) and
rem sound win/loss proofs are NOT delayed. Synergises with the conversion fix.
set STILLWATER_VERIFY_DRAW=256
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
rem THE AQUIFER: steer value-admissible opening moves toward the engine's own
rem best-realized lines (compounding outcome-memory; band-gated, safe). Reads
rem aquifer.npz (rebuild with tools/build_aquifer.py as games accumulate).
set STILLWATER_AQUIFER=1
rem COURT FIX (2026-07-07 audit, see stillwater_uci_cuda.bat for details):
rem spend floor + fresh-evidence stopping confidence.
set STILLWATER_MIN_SPEND=0.35
set STILLWATER_FRESH_P=1
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
