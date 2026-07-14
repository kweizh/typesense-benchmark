#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINARY="${SCRIPT_DIR}/typesense-server"
DATA_DIR="${SCRIPT_DIR}/data"
PID_FILE="${SCRIPT_DIR}/typesense.pid"
LOG_FILE="${SCRIPT_DIR}/typesense.log"
PORT=8108
API_KEY="${TYPESENSE_API_KEY:?TYPESENSE_API_KEY environment variable is not set}"

# Check if the server is already running and healthy
if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo "Typesense server is already running and healthy on port ${PORT}."
    exit 0
fi

# Kill any stale process recorded in the PID file
if [[ -f "${PID_FILE}" ]]; then
    OLD_PID=$(cat "${PID_FILE}")
    if kill -0 "${OLD_PID}" 2>/dev/null; then
        echo "Stopping stale Typesense process (PID ${OLD_PID})..."
        kill "${OLD_PID}" || true
        sleep 1
    fi
    rm -f "${PID_FILE}"
fi

mkdir -p "${DATA_DIR}"

echo "Starting Typesense server on port ${PORT}..."
"${BINARY}" \
    --data-dir="${DATA_DIR}" \
    --api-key="${API_KEY}" \
    --listen-port="${PORT}" \
    --log-dir="${SCRIPT_DIR}" \
    >> "${LOG_FILE}" 2>&1 &

TYPESENSE_PID=$!
echo "${TYPESENSE_PID}" > "${PID_FILE}"

echo "Waiting for Typesense to become healthy (PID ${TYPESENSE_PID})..."
TIMEOUT=60
ELAPSED=0
until curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; do
    if ! kill -0 "${TYPESENSE_PID}" 2>/dev/null; then
        echo "ERROR: Typesense process exited unexpectedly. Check ${LOG_FILE}." >&2
        exit 1
    fi
    if [[ "${ELAPSED}" -ge "${TIMEOUT}" ]]; then
        echo "ERROR: Typesense did not become healthy within ${TIMEOUT}s." >&2
        exit 1
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

echo "Typesense server is healthy on http://localhost:${PORT}"
