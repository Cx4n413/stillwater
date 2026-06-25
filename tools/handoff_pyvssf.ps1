# Wait for the live lichess game to finish, kill the bot tree, then launch the
# current-python-vs-SF decisive cleave. Avoids abandoning the rated game.
$ErrorActionPreference = "Continue"
while ($true) {
    $eng = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
           Where-Object { $_.CommandLine -match 'stillwater\.uci' }
    if (-not $eng) { break }
    Start-Sleep -Seconds 3
}
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match 'lichess-bot\.py|spawn_main|stillwater_uci\.bat' -and
                   $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
& "C:\Users\nonna\Downloads\ExperimentalChessEngine\tools\run_python_vs_sf.cmd"
