FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep jq && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests typesense && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the Typesense standalone native Linux binary (no Docker-in-Docker required).
RUN curl -fsSL -o /tmp/typesense.tar.gz \
        https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Seed the deterministic messy dataset fixture used by the import pipeline.
RUN python3 - <<'PY'
import json
import os

path = "/home/user/import-pipeline/data/raw_products.jsonl"
os.makedirs(os.path.dirname(path), exist_ok=True)

cats = ["home", "garden", "tech", "toys"]
docs = []

# 200 clean, fully-valid documents.
for i in range(1, 201):
    docs.append({
        "id": f"p{i:03d}",
        "sku": f"SKU-{i:04d}",
        "name": f"Product {i}",
        "price": round(10 + i * 0.5, 2),
        "quantity": (i % 50) + 1,
        "category": cats[i % 4],
    })

# 2 documents whose numeric price is a plain numeric string -> coerced on first pass.
docs.append({"id": "c001", "sku": "SKU-C001", "name": "Coercible One", "price": "45.50", "quantity": 5, "category": "tech"})
docs.append({"id": "c002", "sku": "SKU-C002", "name": "Coercible Two", "price": "1099.99", "quantity": 9, "category": "home"})

# 4 fixable documents (repairable via the two allowed transformation rules).
docs.append({"id": "f001", "sku": "SKU-F001", "name": "Currency One", "price": "$1,299.00", "quantity": 3, "category": "tech"})
docs.append({"id": "f002", "sku": "SKU-F002", "name": "Currency Two", "price": "$799.00", "quantity": 7, "category": "home"})
docs.append({"id": "f003", "sku": "SKU-F003", "name": "NoCategory One", "price": 19.99, "quantity": 4})
docs.append({"id": "f004", "sku": "SKU-F004", "name": "NoCategory Two", "price": "$59.50", "quantity": 6})

# 3 unfixable documents (not addressed by the allowed transformation rules).
docs.append({"id": "u001", "name": "Missing Sku", "price": 12.0, "quantity": 2, "category": "toys"})
docs.append({"id": "u002", "sku": "SKU-U002", "price": 15.0, "quantity": 1, "category": "garden"})
docs.append({"id": "u003", "sku": "SKU-U003", "name": "Bad Quantity", "price": 22.0, "quantity": "many", "category": "toys"})

with open(path, "w", encoding="utf-8") as f:
    for d in docs:
        f.write(json.dumps(d) + "\n")
PY

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense standalone-binary environment with a messy JSONL product dataset for a resilient bulk-import + selective-retry pipeline task."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep (plus jq for verification)
#   - always required pip3 packages: pytest-json-ctrf
#   - pip3 packages for the task/verifier: requests, typesense (Python SDK)
#   - Typesense standalone server binary at /usr/local/bin/typesense-server (v26.0)
#   - /home/user/import-pipeline: project directory
#   - /home/user/import-pipeline/data/raw_products.jsonl: 209-document messy JSONL dataset fixture

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
