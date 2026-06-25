# Fetch the complete 3-4-5-man Syzygy set (WDL + DTZ, ~1GB) into nets/syzygy.
# Downloads land in a temp dir and move over only when each file is complete,
# so the engine can never mmap a half-written table. Writes DONE.txt at the end.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\nonna\Downloads\ExperimentalChessEngine"
$dest = Join-Path $repo "nets\syzygy"
$tmp  = Join-Path $repo "nets\syzygy_345_tmp"
$base = "https://tablebase.lichess.ovh/tables/standard"
New-Item -ItemType Directory -Force $tmp | Out-Null
New-Item -ItemType Directory -Force $dest | Out-Null

$log = Join-Path $repo "nets\syzygy_fetch.log"
"start $(Get-Date)" | Out-File -Encoding utf8 $log

# file list from the WDL index page
$idx = (& curl.exe -s --max-time 60 "$base/3-4-5-wdl/")
$names = [regex]::Matches($idx, 'href="([^"]+\.rtbw)"') | ForEach-Object { $_.Groups[1].Value -replace '\.rtbw$','' }
"files: $($names.Count)" | Out-File -Encoding utf8 -Append $log

$jobs = @()
foreach ($n in $names) {
    foreach ($pair in @(@("3-4-5-wdl", "$n.rtbw"), @("3-4-5-dtz", "$n.rtbz"))) {
        $sub = $pair[0]; $f = $pair[1]
        $final = Join-Path $dest $f
        if (Test-Path $final) { continue }   # already have it (the 13-type subset)
        $out = Join-Path $tmp $f
        # cap parallelism at 10
        while (@(Get-Job -State Running).Count -ge 10) { Start-Sleep -Milliseconds 200 }
        $jobs += Start-Job -ScriptBlock {
            param($url, $out)
            & curl.exe -s --retry 3 --max-time 600 -o $out $url
        } -ArgumentList "$base/$sub/$f", $out
    }
}
$jobs | Wait-Job -Timeout 3000 | Out-Null
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue

# move complete files into the live dir (size > 0)
$moved = 0
Get-ChildItem $tmp -File | Where-Object { $_.Length -gt 0 } | ForEach-Object {
    Move-Item -Force $_.FullName (Join-Path $dest $_.Name); $moved++
}
"moved $moved files; total now $((Get-ChildItem $dest -File).Count)" | Out-File -Encoding utf8 -Append $log
"done $(Get-Date)" | Out-File -Encoding utf8 -Append $log
"done" | Out-File -Encoding utf8 (Join-Path $repo "nets\syzygy\DONE.txt")
