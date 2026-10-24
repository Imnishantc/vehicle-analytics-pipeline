# Windows variant of publish_video.sh.
# Usage: .\scripts\publish_video.ps1 -Video traffic.mp4 [-Url rtsp://localhost:8554/traffic] [-Ffmpeg path\to\ffmpeg.exe]
param(
  [Parameter(Mandatory = $true)][string]$Video,
  [string]$Url = $(if ($env:RTSP_PUBLISH_URL) { $env:RTSP_PUBLISH_URL } else { 'rtsp://localhost:8554/traffic' }),
  [string]$Ffmpeg = 'ffmpeg'
)
if (-not (Test-Path $Video)) { Write-Error "video not found: $Video"; exit 1 }
while ($true) {
  & $Ffmpeg -hide_banner -re -stream_loop -1 -i $Video -an -c:v libx264 -preset veryfast `
    -tune zerolatency -pix_fmt yuv420p -g 30 -f rtsp -rtsp_transport tcp $Url
  Write-Warning "publisher exited ($LASTEXITCODE), retrying in 3s (Ctrl+C to stop)"
  Start-Sleep -Seconds 3
}
