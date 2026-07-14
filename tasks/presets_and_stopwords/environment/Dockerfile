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
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the standalone native Typesense server binary (per research plan).
RUN curl -fsSL -o /tmp/typesense-server.tar.gz \
        "https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz" && \
    tar -xzf /tmp/typesense-server.tar.gz -C /usr/local/bin typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/typesense-app

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense standalone-binary task environment for building search presets and a stopwords set."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - requests: used by the final-state pytest checks to call the Typesense REST API
#   - Typesense server v26.0 standalone binary installed at /usr/local/bin/typesense-server
#   - /home/user/typesense-app: working directory for the task

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
