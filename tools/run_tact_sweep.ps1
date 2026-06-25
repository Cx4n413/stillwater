# Per-bit attribution sweep: WAC-300 at 1000ms for each single Refine bit.
# Baselines already on disk: old (mask 0) 284/300, full package (0xFF) 268/300.
Set-Location "C:\Users\nonna\Downloads\ExperimentalChessEngine"
"=== SWEEP starting $(Get-Date) ===" | Out-File -Append -Encoding ascii games\tact_sweep.log
foreach ($m in 1, 2, 4, 8, 16, 32, 64, 128) {
    $env:STILLWATER_REFINE_MASK = "$m"
    & C:\Users\nonna\miniconda3\python.exe -u tools\tactical_bench.py --engine sw --movetime 1000 --tag "m$m" 2>&1 |
        Out-File -Append -Encoding ascii games\tact_sweep.log
}
Remove-Item Env:\STILLWATER_REFINE_MASK
"SWEEP DONE $(Get-Date)" | Out-File -Append -Encoding ascii games\tact_sweep.log
