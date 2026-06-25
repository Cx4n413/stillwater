@echo off
rem STILLWATER UCI with the honest-max backup correction ENABLED (per-engine env
rem for cutechess A/B). The value is set from the sweep winner before the match.
set STILLWATER_HONEST_K=0.05
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
