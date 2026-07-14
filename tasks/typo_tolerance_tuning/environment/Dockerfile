FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests "typesense>=0.21.0" && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the standalone Typesense server binary (native Linux, no Docker-in-Docker).
RUN curl -fsSL -o /tmp/typesense-server.tar.gz \
        https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense-server.tar.gz -C /tmp && \
    mv /tmp/typesense-server /usr/local/bin/typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Seed the product dataset the executor must index into the `catalog` collection.
RUN mkdir -p /home/user/typo-tuning && \
    cat >/home/user/typo-tuning/products.jsonl <<'EOF'
{"id": "1", "name": "Wireless Mouse", "brand": "Logitech"}
{"id": "2", "name": "Mechanical Keyboard", "brand": "Keychron"}
{"id": "3", "name": "Camera Bag", "brand": "Nikon"}
{"id": "4", "name": "Gaming Headset", "brand": "Corsair"}
{"id": "5", "name": "USB Cable", "brand": "Anker"}
{"id": "6", "name": "Portable Charger", "brand": "Anker"}
{"id": "7", "name": "Basketball Shoes", "brand": "Nike"}
{"id": "8", "name": "Water Bottle", "brand": "Hydro"}
{"id": "9", "name": "Wifi Router", "brand": "Netgear"}
{"id": "10", "name": "Beach Bag", "brand": "Coast"}
{"id": "11", "name": "Charter Bus", "brand": "Metro"}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense typo-tolerance tuning task: standalone Typesense v26.0 binary plus a seeded product dataset."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - pip3 packages for tests/task: requests, typesense (Python SDK)
#   - Typesense server v26.0 standalone binary at /usr/local/bin/typesense-server
#   - /home/user/typo-tuning: project directory
#   - /home/user/typo-tuning/products.jsonl: seed dataset (11 products) to index into the `catalog` collection

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
