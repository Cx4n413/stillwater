# Verification match: STILLWATER vs Stockfish 18 at a capped UCI_Elo.
# Usage examples:
#   .\tools\run_match.ps1                          # 20 games vs SF@3000, 60+0.6
#   .\tools\run_match.ps1 -Elo 3190 -Games 30
#   .\tools\run_match.ps1 -TC "120+1" -Mock        # plumbing check on mock oracle
param(
    [int]$Elo = 3000,
    [int]$Games = 20,
    [string]$TC = "60+0.6",
    [string]$PgnOut = "match_results.pgn",
    [switch]$Mock
)

$repo = Split-Path -Parent $PSScriptRoot
$cutechess = "C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe"
$stockfish = "C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"

if (-not (Test-Path $cutechess)) { throw "cutechess-cli not found at $cutechess" }
if (-not (Test-Path $stockfish)) { throw "stockfish not found at $stockfish" }

$stillwaterArgs = @(
    "name=STILLWATER", "cmd=python", "arg=-m", "arg=stillwater.uci",
    "dir=$repo", "proto=uci", "restart=off"
)
if ($Mock) { $stillwaterArgs += "option.UseMock=true" }

$rounds = [math]::Ceiling($Games / 2)

& $cutechess `
    -engine @stillwaterArgs `
    -engine name=SF18-$Elo cmd=$stockfish proto=uci `
        option.UCI_LimitStrength=true option.UCI_Elo=$Elo option.Threads=1 `
    -each tc=$TC timemargin=2500 `
    -rounds $rounds -games 2 -repeat `
    -recover `
    -draw movenumber=80 movecount=10 score=10 `
    -resign movecount=5 score=1000 `
    -ratinginterval 2 `
    -pgnout (Join-Path $repo $PgnOut)
