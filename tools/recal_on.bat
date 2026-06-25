@echo off
rem Launch STILLWATER UCI with the Tier-2 value recalibration ENABLED.
rem Used as the cutechess engine cmd for the recal arm so the env toggle is
rem per-engine (cutechess shares one environment across engines otherwise).
set STILLWATER_RECAL=1
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
