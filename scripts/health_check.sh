#!/usr/bin/env bash
# Quick end-to-end health probe: MediaMTX path, API, DB, pipeline heartbeat.
API="${API_URL:-http://localhost:8000}"
MTX="${MEDIAMTX_API:-http://localhost:9997}"
ok=0
echo "== MediaMTX paths";  curl -fsS "$MTX/v3/paths/list" | head -c 600 || { echo "MediaMTX API unreachable"; ok=1; }
echo; echo "== API health";  curl -fsS "$API/api/health" || { echo "API unreachable"; ok=1; }
echo; echo "== Stream status"; curl -fsS "$API/api/streams/status" || ok=1
echo; exit $ok
