# Morning launcher for the v3 (fine-tuned BT4) vs baseline gauntlet.
# SAFETY: refuses to run while the live Lichess bot is up (GPU contention would
# sabotage real rated games). Pause the bot first, then run this.
$bot = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'lichess-bot' }
if ($bot) {
    Write-Output ("LIVE BOT RUNNING (pid " + ($bot.ProcessId -join ',') +
        "). Pause it first, then re-run. Gauntlet NOT started.")
    exit 1
}
Write-Output "Bot is down. Launching v3-vs-base gauntlet (fixed 800 nodes, SPRT, cap 200 games)..."
Set-Location "C:\Users\nonna\Downloads\ExperimentalChessEngine"
& cmd /c "tools\run_ftnet_ab.cmd"
Write-Output "=== Gauntlet finished. Tail of log: ==="
if (Test-Path "games\ftnet_ab.log") { Get-Content "games\ftnet_ab.log" -Tail 18 }
