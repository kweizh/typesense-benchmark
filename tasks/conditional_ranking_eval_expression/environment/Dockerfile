FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests typesense && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the standalone Typesense server binary (native Linux amd64, no Docker-in-Docker).
RUN curl -fsSL -o /tmp/typesense-server.tar.gz \
        https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense-server.tar.gz -C /tmp && \
    mv /tmp/typesense-server /usr/local/bin/typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/typesense-ranking

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense standalone-binary environment for building custom relevance ranking with sort_by _eval() conditional scoring."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - pip3 packages for verification/execution: requests, typesense (Python SDK)
#   - Typesense server v26.0 standalone binary at /usr/local/bin/typesense-server (run natively on port 8108)
#   - /home/user/typesense-ranking: project directory where the executor implements setup.py and rank.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
