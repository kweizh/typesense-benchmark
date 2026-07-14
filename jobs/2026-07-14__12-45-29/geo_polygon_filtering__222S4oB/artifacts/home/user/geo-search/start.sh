#!/usr/bin/env bash
# Starts a local Typesense server on localhost:8108 with the API key from
# $TYPESENSE_API_KEY. Safe to invoke when a server is already running: in
# that case it simply waits for /health to respond and returns.
#
# The server runs as a detached, long-lived process so that data survives
# between the seed step and later search steps.

set -u

DATA_DIR="${TYPESENSE_DATA_DIR:-/home/user/geo-search/typesense-data}"
LOG_FILE="${TYPESENSE_LOG_FILE:-/home/user/geo-search/typesense.log}"
PID_FILE="${TYPESENSE_PID_FILE:-/home/user/geo-search/typesense.pid}"
HOST="${TYPESENSE_HOST:-localhost}"
PORT="${TYPESENSE_PORT:-8108}"
HEALTH_URL="http://${HOST}:${PORT}/health"
WAIT_SECONDS=60

if [[ -z "${TYPESENSE_API_KEY:-}" ]]; then
    echo "ERROR: TYPESENSE_API_KEY environment variable must be set" >&2
    exit 1
fi

mkdir -p "${DATA_DIR}"

# If a healthy Typesense is already serving on the target port, we're done.
ready() {
    # /health returns 200 with {"ok":true} when Typesense is healthy.
    local body
    body=$(curl -sS --max-time 3 "${HEALTH_URL}" 2>/dev/null) || return 1
    [[ "${body}" == *'"ok":true'* ]]
}

if ready; then
    exit 0
fi

# No healthy server yet. Launch one in the background, detached from this shell.
nohup /usr/local/bin/typesense-server \
    --data-dir="${DATA_DIR}" \
    --api-key="${TYPESENSE_API_KEY}" \
    --api-address="0.0.0.0" \
    --api-port="${PORT}" \
    --enable-cors \
    > "${LOG_FILE}" 2>&1 &
SERVER_PID=$!
echo "${SERVER_PID}" > "${PID_FILE}"

# Poll /health until it returns ok (or we time out).
deadline=$(( $(date +%s) + WAIT_SECONDS ))
while (( $(date +%s) < deadline )); do
    if ready; then
        exit 0
    fi
    # If the process died, fail fast rather than waiting the full timeout.
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo "ERROR: Typesense server exited before becoming healthy. See ${LOG_FILE}" >&2
        exit 1
    fi
    sleep 1
done

echo "ERROR: Typesense server did not become healthy within ${WAIT_SECONDS}s. See ${LOG_FILE}" >&2
exit 1
