#!/usr/bin/env bash
# Loop an MP4 into MediaMTX over RTSP. Re-publishes automatically if the connection drops.
# Usage: scripts/publish_video.sh path/to/traffic.mp4 [rtsp://host:8554/traffic]
set -u
VIDEO="${1:?usage: publish_video.sh <video.mp4> [rtsp_url]}"
URL="${2:-${RTSP_PUBLISH_URL:-rtsp://localhost:8554/traffic}}"
FFMPEG="${FFMPEG:-ffmpeg}"
[ -f "$VIDEO" ] || { echo "video not found: $VIDEO" >&2; exit 1; }
trap 'echo "stopping publisher"; exit 0' INT TERM
while true; do
  # -re: real-time pacing; -stream_loop -1: loop forever; copy H.264 without re-encoding.
  "$FFMPEG" -hide_banner -re -stream_loop -1 -i "$VIDEO" -an -c:v libx264 -preset veryfast \
    -tune zerolatency -pix_fmt yuv420p -g 30 -f rtsp -rtsp_transport tcp "$URL"
  echo "publisher exited ($?), retrying in 3s..." >&2
  sleep 3
done
