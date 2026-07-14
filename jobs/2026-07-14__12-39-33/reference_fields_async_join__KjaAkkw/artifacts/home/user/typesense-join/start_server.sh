#!/usr/bin/env bash
# start_server.sh — Start the Typesense server and wait for it to be healthy.
# Usage: TYPESENSE_API_KEY=xyz ./start_server.sh

set -euo pipefail

API_KEY="${TYPESENSE_API_KEY:-xyz}"
DATA_DIR="/home/user/typesense-join/typesense-data"
LOG_DIR="/home/user/typesense-join/logs"
PORT=8108

mkdir -p "$DATA_DIR" "$LOG_DIR"

# Kill any existing server on the same port
pkill -f "typesense-server.*--api-port=${PORT}" 2>/dev/null || true
sleep 1

echo "[server] Starting Typesense on port ${PORT}…"
/usr/local/bin/typesense-server \
    --data-dir="$DATA_DIR" \
    --api-key="$API_KEY" \
    --api-port="$PORT" \
    --log-dir="$LOG_DIR" \
    &

# Wait for healthy
echo "[server] Waiting for health check…"
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${PORT}/health" | grep -q '"ok":true'; then
        echo "[server] Typesense is healthy."
        exit 0
    fi
    sleep 1
done
echo "[server] ERROR: Typesense did not become healthy within 30 s."
exit 1
