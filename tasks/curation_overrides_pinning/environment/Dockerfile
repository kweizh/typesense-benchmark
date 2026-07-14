FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests && \
    curl -fsSL -o /tmp/typesense-server.tar.gz \
        https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense-server.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/typesense-curation

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense v26.0 standalone binary environment for a search curation/overrides (pinning, hiding, dynamic filtering) task."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - requests: used by test_initial_state.py and test_final_state.py for HTTP API verification
#   - typesense-server v26.0 standalone Linux binary installed at /usr/local/bin/typesense-server
#   - /home/user/typesense-curation: project directory where the executor sets up the server, data, and overrides

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
