FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests pytest-xprocess typesense && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the standalone native Typesense server binary (no Docker-in-Docker needed).
RUN curl -fsSL -o /tmp/typesense-server.tar.gz \
        "https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz" && \
    tar -xzf /tmp/typesense-server.tar.gz -C /usr/local/bin typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Project directory, data directory, and the standalone server data directory.
RUN mkdir -p /home/user/federated-search/data && \
    mkdir -p /home/user/federated-search/typesense-data

# Seed the heterogeneous sample datasets (JSONL) used by the federated search task.
RUN cat >/home/user/federated-search/data/products.jsonl <<'EOF'
{"id": "p1", "product_name": "Wireless Mouse", "category": "Electronics", "price": 29.99}
{"id": "p2", "product_name": "Mechanical Keyboard", "category": "Electronics", "price": 89.99}
{"id": "p3", "product_name": "Running Shoes", "category": "Footwear", "price": 75.0}
{"id": "p4", "product_name": "Wireless Headphones", "category": "Electronics", "price": 120.0}
EOF

RUN cat >/home/user/federated-search/data/articles.jsonl <<'EOF'
{"id": "a1", "title": "The Future of Wireless Charging", "body": "An in-depth look at wireless power delivery.", "author": "Jane Doe"}
{"id": "a2", "title": "Mechanical Keyboards 101", "body": "A beginner guide to switches.", "author": "John Smith"}
{"id": "a3", "title": "Running Form Tips", "body": "How to improve your running technique.", "author": "Jane Doe"}
EOF

RUN cat >/home/user/federated-search/data/users.jsonl <<'EOF'
{"id": "u1", "username": "wireless_wizard", "full_name": "Will Reless", "bio": "Loves gadgets"}
{"id": "u2", "username": "keyboard_king", "full_name": "Kevin King", "bio": "Mechanical keyboard enthusiast"}
{"id": "u3", "username": "runner_jane", "full_name": "Jane Doe", "bio": "Marathon runner"}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense standalone-binary environment for a federated multi_search task, seeded with products/articles/users JSONL datasets."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - extra pip3 packages for verification: requests, pytest-xprocess, typesense (Python SDK)
#   - Typesense standalone server binary installed at /usr/local/bin/typesense-server (v26.0)
#   - /home/user/federated-search: task project directory
#   - /home/user/federated-search/data: products.jsonl, articles.jsonl, users.jsonl sample datasets
#   - /home/user/federated-search/typesense-data: data-dir for the standalone Typesense server

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
