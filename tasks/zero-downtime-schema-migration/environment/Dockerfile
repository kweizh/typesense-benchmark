FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the Typesense standalone native Linux binary (v26.0).
RUN curl -fsSL -o /tmp/typesense.tar.gz \
        https://dl.typesense.org/releases/26.0/typesense-server-26.0-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Create the project directory, the data directory, and a helper start script.
RUN mkdir -p /home/user/project/typesense-data
RUN cat > /home/user/project/start-typesense.sh <<'EOF'
#!/usr/bin/env bash
# Start the Typesense server against the seeded on-disk data directory.
mkdir -p /home/user/project/typesense-data
nohup /usr/local/bin/typesense-server \
  --data-dir=/home/user/project/typesense-data \
  --api-key=xyz \
  --port=8108 \
  --enable-cors > /home/user/project/typesense.log 2>&1 &
EOF
RUN chmod +x /home/user/project/start-typesense.sh

# Seed the initial state: a populated `products_v1` collection (rating is int32)
# and a `products` alias pointing to it. This is baked into the persisted
# data directory so a later server restart reloads the exact same state.
RUN cat > /tmp/seed.sh <<'EOF'
#!/usr/bin/env bash
/usr/local/bin/typesense-server \
  --data-dir=/home/user/project/typesense-data \
  --api-key=xyz \
  --port=8108 \
  --enable-cors > /tmp/ts-seed.log 2>&1 &
TS_PID=$!

for i in $(seq 1 60); do
  if curl -s http://localhost:8108/health | grep -q '"ok":true'; then
    break
  fi
  sleep 1
done
if ! curl -s http://localhost:8108/health | grep -q '"ok":true'; then
  echo "Typesense did not become healthy during seeding" >&2
  cat /tmp/ts-seed.log >&2
  exit 1
fi

curl -sf "http://localhost:8108/collections" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-TYPESENSE-API-KEY: xyz" \
  -d '{
    "name": "products_v1",
    "fields": [
      {"name": "name", "type": "string"},
      {"name": "category", "type": "string", "facet": true},
      {"name": "rating", "type": "int32"},
      {"name": "price", "type": "float"}
    ],
    "default_sorting_field": "rating"
  }' || { echo "collection create failed" >&2; exit 1; }

IMPORT_RESULT=$(curl -sf "http://localhost:8108/collections/products_v1/documents/import?action=create" \
  -X POST \
  -H "X-TYPESENSE-API-KEY: xyz" \
  -H "Content-Type: text/plain" \
  --data-binary @- <<'DOCS'
{"id":"1","name":"Wireless Mouse","category":"Electronics","rating":4,"price":29.99}
{"id":"2","name":"Mechanical Keyboard","category":"Electronics","rating":5,"price":89.99}
{"id":"3","name":"USB-C Cable","category":"Electronics","rating":3,"price":9.5}
{"id":"4","name":"Desk Lamp","category":"Home","rating":4,"price":24.0}
{"id":"5","name":"Coffee Mug","category":"Home","rating":5,"price":12.5}
{"id":"6","name":"Notebook","category":"Office","rating":2,"price":4.99}
{"id":"7","name":"Standing Desk","category":"Office","rating":5,"price":299.0}
{"id":"8","name":"Ergonomic Chair","category":"Office","rating":4,"price":199.99}
{"id":"9","name":"Water Bottle","category":"Sports","rating":3,"price":15.0}
{"id":"10","name":"Yoga Mat","category":"Sports","rating":4,"price":25.0}
{"id":"11","name":"Running Shoes","category":"Sports","rating":5,"price":79.99}
{"id":"12","name":"Bluetooth Speaker","category":"Electronics","rating":4,"price":49.99}
DOCS
)
if echo "$IMPORT_RESULT" | grep -q '"success":false'; then
  echo "document import failed: $IMPORT_RESULT" >&2
  exit 1
fi

curl -sf "http://localhost:8108/aliases/products" \
  -X PUT \
  -H "Content-Type: application/json" \
  -H "X-TYPESENSE-API-KEY: xyz" \
  -d '{"collection_name": "products_v1"}' || { echo "alias create failed" >&2; exit 1; }

NUM_DOCS=$(curl -sf "http://localhost:8108/collections/products_v1" \
  -H "X-TYPESENSE-API-KEY: xyz" | grep -o '"num_documents":[0-9]*' | grep -o '[0-9]*')
if [ "$NUM_DOCS" != "12" ]; then
  echo "expected 12 seeded documents, got '$NUM_DOCS'" >&2
  exit 1
fi

# Cleanly stop the server so all state is flushed to the data directory.
kill "$TS_PID"
wait "$TS_PID" 2>/dev/null || true
echo "Seeding complete: products_v1 (12 docs, rating int32) + alias products -> products_v1"
EOF
RUN bash /tmp/seed.sh && rm -f /tmp/seed.sh

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense v26.0 environment pre-seeded with a populated products_v1 collection (rating int32) and a products alias, for a zero-downtime schema migration task."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - pip3 package requests: used by the initial/final state pytest checks to call the Typesense HTTP API
#   - Typesense server v26.0 standalone binary at /usr/local/bin/typesense-server
#   - /home/user/project: task project directory
#   - /home/user/project/typesense-data: persisted data dir seeded with collection products_v1 + alias products
#   - /home/user/project/start-typesense.sh: helper to launch the server against the seeded data dir on port 8108 (api-key=xyz)

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
