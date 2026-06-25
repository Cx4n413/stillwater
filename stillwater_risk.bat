@echo off
rem TREATMENT arm for the #1 distribution-native risk-utility A/B.
rem Identical to the deployed stillwater_uci.bat PLUS the risk posture, so the
rem ONLY difference vs the baseline arm is the readout change under test.
rem First test = RISK-AVERSE (shrink the loss tail), fires always so it is
rem exercised in peer self-play. Flip STILLWATER_RISK to a negative value for
rem the risk-seeking direction; set STILLWATER_RISK_GATE=weak to gate on rho.
set STILLWATER_RISK=0.5
set STILLWATER_RISK_GATE=always
set STILLWATER_RISK_BAND=0.10
rem --- deployed config (must match stillwater_uci.bat exactly) ---
set STILLWATER_CONVERT=1
set STILLWATER_VERIFY_DRAW=256
set STILLWATER_LCB_K=0.0
set STILLWATER_FPU_RED=0.22
set STILLWATER_ML_THRESH=0.9
set STILLWATER_CPUCT_INIT=2.045
set STILLWATER_CPUCT_FACTOR=4.894
set STILLWATER_C_VAR=0.2
set STILLWATER_PICK_K=1.1
cd /d "%~dp0"
"C:\Users\nonna\miniconda3\python.exe" -u -m stillwater.uci
