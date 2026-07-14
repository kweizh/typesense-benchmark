FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests typesense && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the Typesense standalone native Linux binary (v26.0) into /usr/local/bin.
RUN curl -fsSL -o /tmp/typesense-server.tar.gz \
        https://dl.typesense.org/releases/26.0/typesense-server-26.0-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense-server.tar.gz -C /usr/local/bin && \
    rm /tmp/typesense-server.tar.gz && \
    chmod +x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Seed the project directory with the deeply nested customer/orders dataset.
RUN mkdir -p /home/user/nested-search/data && \
    cat >/home/user/nested-search/data/orders.jsonl <<'EOF'
{"id": "cust_1", "customer_name": "Alice", "orders": [{"order_id": "o1", "line_items": [{"sku": "S1", "name": "Wireless Mouse", "category": "Electronics", "price": 29.99, "attributes": {"color": "black", "material": "plastic"}}, {"sku": "S2", "name": "USB Cable", "category": "Electronics", "price": 9.99, "attributes": {"color": "white", "material": "rubber"}}]}]}
{"id": "cust_2", "customer_name": "Bob", "orders": [{"order_id": "o2", "line_items": [{"sku": "S3", "name": "Ceramic Mug", "category": "Kitchen", "price": 12.5, "attributes": {"color": "blue", "material": "ceramic"}}]}, {"order_id": "o3", "line_items": [{"sku": "S4", "name": "Wireless Keyboard", "category": "Electronics", "price": 49.99, "attributes": {"color": "black", "material": "plastic"}}]}]}
{"id": "cust_3", "customer_name": "Carol", "orders": [{"order_id": "o4", "line_items": [{"sku": "S5", "name": "Leather Wallet", "category": "Accessories", "price": 39.99, "attributes": {"color": "brown", "material": "leather"}}, {"sku": "S6", "name": "Wireless Charger", "category": "Electronics", "price": 19.99, "attributes": {"color": "white", "material": "plastic"}}]}]}
{"id": "cust_4", "customer_name": "Dave", "orders": [{"order_id": "o5", "line_items": [{"sku": "S7", "name": "Steel Water Bottle", "category": "Kitchen", "price": 24.99, "attributes": {"color": "silver", "material": "steel"}}, {"sku": "S8", "name": "Ceramic Bowl", "category": "Kitchen", "price": 14.99, "attributes": {"color": "blue", "material": "ceramic"}}]}]}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense standalone-binary environment for deeply nested object indexing and querying."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - pip3 packages for tests/agent: requests, typesense (Python SDK)
#   - Typesense server v26.0 standalone binary at /usr/local/bin/typesense-server
#   - /home/user/nested-search: project directory
#   - /home/user/nested-search/data/orders.jsonl: seed dataset of 4 deeply nested customer documents

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
