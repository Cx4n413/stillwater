# Waits for any in-progress lichess game to end (engine process exits),
# then immediately kills the whole bot tree before matchmaking can start
# another game. Prints one line on success so a Monitor can pick it up.
$ErrorActionPreference = "Continue"
try {
    while ($true) {
        $eng = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
               Where-Object { $_.CommandLine -match 'stillwater\.uci' }
        if (-not $eng) { break }
        Start-Sleep -Seconds 2
    }
    # engine gone = game over. Kill the bot tree NOW, before the matchmaker
    # issues the next challenge.
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match 'lichess-bot\.py|spawn_main|stillwater_uci\.bat' -and
                       $_.ProcessId -ne $PID } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    $left = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -match 'lichess|stillwater' }
    if ($left) { "BOT-STOP-PARTIAL: $(($left | ForEach-Object ProcessId) -join ',')" }
    else { "BOT-STOPPED: GPU free" }
} catch {
    "MONITOR-ERROR: $_"
}
