FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    curl -fsSL "https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz" -o /tmp/typesense.tar.gz && \
    tar -xzf /tmp/typesense.tar.gz -C /usr/local/bin typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense.tar.gz && \
    pip3 install --break-system-packages pytest-json-ctrf requests "typesense>=0.19,<1.0" && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/geo-search

# Arbitrary demo API key for the local single-node Typesense server (not a real secret).
# Baking it in keeps the task fully self-contained and deterministic for both the
# executor and the verifier.
ENV TYPESENSE_API_KEY=xyz

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense geosearch task environment with the standalone typesense-server binary and the Python SDK installed."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - typesense-server standalone native binary (v26.0) installed at /usr/local/bin/typesense-server
#   - pip3 packages for verification: requests, typesense (Python SDK)
#   - /home/user/geo-search: empty project directory for the executor's geo-polygon search implementation

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
