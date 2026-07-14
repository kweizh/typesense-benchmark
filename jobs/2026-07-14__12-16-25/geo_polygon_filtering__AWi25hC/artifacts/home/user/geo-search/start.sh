#!/bin/bash
set -e

# Ensure data directory exists
mkdir -p /home/user/geo-search/data

# Check if typesense-server is already running and healthy on port 8108
is_healthy() {
    local status_code
    status_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8108/health || true)
    if [ "$status_code" -eq 200 ]; then
        return 0
    else
        return 1
    fi
}

if is_healthy; then
    echo "Typesense server is already running and healthy."
    exit 0
fi

echo "Starting Typesense server..."
if [ -z "$TYPESENSE_API_KEY" ]; then
    echo "Error: TYPESENSE_API_KEY is not set." >&2
    exit 1
fi

/usr/local/bin/typesense-server \
    --data-dir=/home/user/geo-search/data \
    --api-key="$TYPESENSE_API_KEY" \
    --api-port=8108 \
    --enable-cors=true \
    > /home/user/geo-search/typesense.log 2>&1 &

# Wait for Typesense to become healthy
echo "Waiting for Typesense server to become healthy..."
timeout=30
elapsed=0
while ! is_healthy; do
    sleep 0.5
    elapsed=$((elapsed + 1))
    if [ "$elapsed" -gt "$((timeout * 2))" ]; then
        echo "Error: Typesense server failed to become healthy within $timeout seconds." >&2
        echo "Tail of logs:" >&2
        tail -n 20 /home/user/geo-search/typesense.log >&2
        exit 1
    fi
done

echo "Typesense server is up and healthy."
