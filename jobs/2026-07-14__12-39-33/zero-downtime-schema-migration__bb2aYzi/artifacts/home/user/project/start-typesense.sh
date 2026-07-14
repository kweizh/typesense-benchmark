#!/usr/bin/env bash
# Start the Typesense server against the seeded on-disk data directory.
mkdir -p /home/user/project/typesense-data
nohup /usr/local/bin/typesense-server \
  --data-dir=/home/user/project/typesense-data \
  --api-key=xyz \
  --port=8108 \
  --enable-cors > /home/user/project/typesense.log 2>&1 &
