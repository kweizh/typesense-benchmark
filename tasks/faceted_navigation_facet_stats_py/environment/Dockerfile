FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    curl -fsSL -o /tmp/typesense.tar.gz https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense.tar.gz -C /usr/local/bin && \
    rm -f /tmp/typesense.tar.gz && \
    chmod +x /usr/local/bin/typesense-server && \
    pip3 install --break-system-packages pytest-json-ctrf requests pytest-xprocess typesense && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/facet-nav/data && \
    cat >/home/user/facet-nav/data/products.jsonl <<'EOF'
{"id":"1","product_name":"Apple MacBook Air","brand":"Apple","category":"Laptops","tags":["portable","premium"],"price":999.0,"rating":4.7}
{"id":"2","product_name":"Apple MacBook Pro","brand":"Apple","category":"Laptops","tags":["premium","pro"],"price":1999.0,"rating":4.8}
{"id":"3","product_name":"Dell XPS 13","brand":"Dell","category":"Laptops","tags":["portable","premium"],"price":1299.0,"rating":4.5}
{"id":"4","product_name":"Dell Inspiron 15","brand":"Dell","category":"Laptops","tags":["budget"],"price":599.0,"rating":4.0}
{"id":"5","product_name":"HP Spectre x360","brand":"HP","category":"Laptops","tags":["premium","portable"],"price":1399.0,"rating":4.4}
{"id":"6","product_name":"Samsung Galaxy Book","brand":"Samsung","category":"Laptops","tags":["portable"],"price":899.0,"rating":4.2}
{"id":"7","product_name":"Apple iPhone 15","brand":"Apple","category":"Phones","tags":["premium"],"price":799.0,"rating":4.6}
{"id":"8","product_name":"Samsung Galaxy S24","brand":"Samsung","category":"Phones","tags":["premium","portable"],"price":899.0,"rating":4.5}
{"id":"9","product_name":"Sony WH-1000XM5","brand":"Sony","category":"Headphones","tags":["premium","audio"],"price":399.0,"rating":4.9}
{"id":"10","product_name":"Sony Bravia TV","brand":"Sony","category":"TVs","tags":["home"],"price":1499.0,"rating":4.3}
{"id":"11","product_name":"Samsung QLED TV","brand":"Samsung","category":"TVs","tags":["home","premium"],"price":1799.0,"rating":4.4}
{"id":"12","product_name":"Dell UltraSharp Monitor","brand":"Dell","category":"Monitors","tags":["budget","portable"],"price":299.0,"rating":4.1}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense faceted-navigation task: standalone typesense-server binary, Python SDK, and a fixed 12-product dataset in /home/user/facet-nav."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Typesense v26.0 standalone server binary at /usr/local/bin/typesense-server
#   - pip3 packages for the task/verifier: typesense (Python SDK), requests, pytest-xprocess
#   - /home/user/facet-nav: project directory for the executor
#   - /home/user/facet-nav/data/products.jsonl: fixed 12-product dataset to be indexed

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
