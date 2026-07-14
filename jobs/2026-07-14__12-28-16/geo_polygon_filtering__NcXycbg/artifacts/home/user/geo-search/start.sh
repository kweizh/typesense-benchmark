#!/usr/bin/env bash
#
# start.sh – Launch a local Typesense server on localhost:8108 and block
# until it is healthy.  Safe to call when the server is already running.
#
set -euo pipefail

API_KEY="${TYPESENSE_API_KEY:?TYPESENSE_API_KEY environment variable is required}"
DATA_DIR="/home/user/geo-search/typesense-data"
LOG_DIR="/home/user/geo-search/typesense-logs"
PID_FILE="/home/user/geo-search/typesense.pid"
PORT=8108
HOST="localhost"

mkdir -p "$DATA_DIR" "$LOG_DIR"

# ------------------------------------------------------------------
# If the server is already running and healthy, we are done.
# ------------------------------------------------------------------
if curl -fsS "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    echo "Typesense server already running on port ${PORT}."
    exit 0
fi

# Clean up a stale PID file (process no longer alive)
if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${OLD_PID}" ]] && ! kill -0 "$OLD_PID" 2>/dev/null; then
        rm -f "$PID_FILE"
    fi
fi

# ------------------------------------------------------------------
# Start the Typesense server in the background.
# ------------------------------------------------------------------
echo "Starting Typesense server on port ${PORT} ..."
nohup typesense-server \
    --data-dir="$DATA_DIR" \
    --api-key="$API_KEY" \
    --api-port="$PORT" \
    --api-address="0.0.0.0" \
    --log-dir="$LOG_DIR" \
    >"${LOG_DIR}/stdout.log" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" >"$PID_FILE"

# ------------------------------------------------------------------
# Wait for the health endpoint to report healthy (up to ~60 s).
# ------------------------------------------------------------------
echo "Waiting for Typesense to become healthy ..."
for _ in $(seq 1 120); do
    if curl -fsS "http://${HOST}:${PORT}/health" 2>/dev/null | grep -q '"ok":true'; then
        echo "Typesense server is healthy (PID ${SERVER_PID})."
        exit 0
    fi
    sleep 0.5
done

echo "ERROR: Typesense server did not become healthy in time." >&2
exit 1