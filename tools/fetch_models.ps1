# Fetch STILLWATER neural-net weights.
#
# The model files (~1.5 GB) are NOT stored in git -- they exceed GitHub's free
# 1 GB LFS quota -- so they ship as assets on a GitHub Release and are pulled
# into nets/ by this script.
#
#   Usage:  pwsh tools/fetch_models.ps1
#   Alt:    gh release download models-v1 -R Cx4n413/stillwater -D nets
#
$ErrorActionPreference = "Stop"
$repo = "Cx4n413/stillwater"
$tag  = "models-v1"
$dest = Resolve-Path (Join-Path $PSScriptRoot "..\nets")
$models = @(
  "BT4-1024x15x32h-policytune.onnx",
  "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz",
  "BT4-embed.onnx",
  "fallback.onnx",
  "t1-256x10-distilled-swa-2432500.pb.gz",
  "t3-512x15x16h-distill-swa-2767500.pb.gz",
  "t3-512x15x16h-distill.onnx"
)
foreach ($m in $models) {
  $out = Join-Path $dest $m
  if (Test-Path $out) { Write-Host "have   $m"; continue }
  $url = "https://github.com/$repo/releases/download/$tag/$m"
  Write-Host "fetch  $m ..."
  Invoke-WebRequest -Uri $url -OutFile $out
}
Write-Host "done -- models in $dest"
