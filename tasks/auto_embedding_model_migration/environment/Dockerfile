FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep jq && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the Typesense v26.0 standalone native Linux binary (no Docker-in-Docker).
RUN mkdir -p /tmp/ts && \
    curl -fsSL -o /tmp/ts/typesense.tar.gz \
        https://dl.typesense.org/releases/26.0/typesense-server-26.0-linux-amd64.tar.gz && \
    tar -xzf /tmp/ts/typesense.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -rf /tmp/ts && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Startup helper: idempotently (re)start the Typesense server on port 8108
# against the pre-seeded data directory. Reads the API key from the environment.
RUN mkdir -p /var/lib/typesense/data && \
    cat >/usr/local/bin/start-typesense.sh <<'EOF'
#!/usr/bin/env bash
API_KEY="${TYPESENSE_API_KEY:-xyz}"
DATA_DIR="/var/lib/typesense/data"
mkdir -p "$DATA_DIR"
if curl -s http://127.0.0.1:8108/health | grep -q '"ok":true'; then
  exit 0
fi
nohup /usr/local/bin/typesense-server \
  --data-dir="$DATA_DIR" \
  --api-key="$API_KEY" \
  --port=8108 \
  --enable-cors >/var/log/typesense.log 2>&1 &
for i in $(seq 1 60); do
  if curl -s http://127.0.0.1:8108/health | grep -q '"ok":true'; then
    exit 0
  fi
  sleep 1
done
echo "Typesense failed to become healthy" >&2
exit 1
EOF
RUN chmod +x /usr/local/bin/start-typesense.sh

# Prepare the agent workspace and the pre-generated 8-dimensional embeddings.
RUN mkdir -p /home/user/migration && \
    cat >/home/user/migration/new_vectors.jsonl <<'EOF'
{"id": "1", "content_embedding": [0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18]}
{"id": "2", "content_embedding": [0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28]}
{"id": "3", "content_embedding": [0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38]}
{"id": "4", "content_embedding": [0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48]}
{"id": "5", "content_embedding": [0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58]}
{"id": "6", "content_embedding": [0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68]}
{"id": "7", "content_embedding": [0.71, 0.72, 0.73, 0.74, 0.75, 0.76, 0.77, 0.78]}
{"id": "8", "content_embedding": [0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88]}
EOF

# Seed the initial `notes` collection (4-dimensional vectors, 8 documents) into the
# persistent data directory at build time by briefly running the server.
RUN cat >/tmp/seed.py <<'EOF'
import json
import requests

URL = "http://127.0.0.1:8108"
H = {"X-TYPESENSE-API-KEY": "xyz"}

schema = {
    "name": "notes",
    "fields": [
        {"name": "title", "type": "string"},
        {"name": "content", "type": "string"},
        {"name": "category", "type": "string", "facet": True},
        {"name": "content_embedding", "type": "float[]", "num_dim": 4},
    ],
}
r = requests.post(f"{URL}/collections", headers=H, json=schema, timeout=30)
print("create collection:", r.status_code, r.text)
r.raise_for_status()

docs = [
    {"id": "1", "title": "Getting Started with Typesense", "category": "guide",
     "content": "Typesense is a fast, typo-tolerant search engine that is easy to get started with.",
     "content_embedding": [0.01, 0.02, 0.03, 0.04]},
    {"id": "2", "title": "Understanding Vector Search", "category": "tutorial",
     "content": "Vector search lets you find semantically similar documents using embeddings.",
     "content_embedding": [0.05, 0.06, 0.07, 0.08]},
    {"id": "3", "title": "Typo Tolerance Explained", "category": "guide",
     "content": "Typo tolerance automatically corrects misspellings in user queries.",
     "content_embedding": [0.09, 0.10, 0.11, 0.12]},
    {"id": "4", "title": "Faceted Navigation Basics", "category": "tutorial",
     "content": "Faceted navigation helps users drill down into results by category.",
     "content_embedding": [0.13, 0.14, 0.15, 0.16]},
    {"id": "5", "title": "Scaling Search Clusters", "category": "ops",
     "content": "Search clusters can be scaled horizontally for higher availability.",
     "content_embedding": [0.17, 0.18, 0.19, 0.20]},
    {"id": "6", "title": "Semantic Search with Embeddings", "category": "tutorial",
     "content": "Semantic search uses model-generated embeddings to match meaning, not just keywords.",
     "content_embedding": [0.21, 0.22, 0.23, 0.24]},
    {"id": "7", "title": "Zero Downtime Migrations", "category": "ops",
     "content": "Aliases enable zero downtime migrations between collection versions.",
     "content_embedding": [0.25, 0.26, 0.27, 0.28]},
    {"id": "8", "title": "Filtering and Sorting Results", "category": "guide",
     "content": "You can filter and sort results using flexible query parameters.",
     "content_embedding": [0.29, 0.30, 0.31, 0.32]},
]
payload = "\n".join(json.dumps(d) for d in docs)
r = requests.post(
    f"{URL}/collections/notes/documents/import?action=create",
    headers=H, data=payload, timeout=60,
)
print("import docs:", r.status_code, r.text)
r.raise_for_status()
assert '"success":false' not in r.text, "Document import reported failures."

r = requests.get(f"{URL}/collections/notes", headers=H, timeout=30)
assert r.json().get("num_documents") == 8, "Seed did not create 8 documents."
print("seed complete:", r.status_code)
EOF
RUN nohup /usr/local/bin/typesense-server \
        --data-dir=/var/lib/typesense/data \
        --api-key=xyz --port=8108 --enable-cors >/var/log/typesense-seed.log 2>&1 & \
    for i in $(seq 1 60); do \
        if curl -s http://127.0.0.1:8108/health | grep -q '"ok":true'; then break; fi; \
        sleep 1; \
    done; \
    python3 /tmp/seed.py; \
    seed_rc=$?; \
    pkill -f typesense-server || true; \
    rm -f /tmp/seed.py; \
    exit $seed_rc

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense v26.0 standalone binary with a pre-seeded 'notes' collection (4-dim vector field) for an in-place vector-field dimensionality migration task."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep (plus jq)
#   - always required pip3 packages: pytest-json-ctrf (plus requests for the pytest verifiers)
#   - Typesense v26.0 standalone native Linux binary at /usr/local/bin/typesense-server
#   - /usr/local/bin/start-typesense.sh: idempotent server start helper (port 8108)
#   - /var/lib/typesense/data: persistent data dir pre-seeded with the 'notes' collection
#     (fields: title, content, category, content_embedding=float[] num_dim 4; 8 documents)
#   - /home/user/migration: agent workspace
#   - /home/user/migration/new_vectors.jsonl: pre-generated 8-dimensional embeddings per document id

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
