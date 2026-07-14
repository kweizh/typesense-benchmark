FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=30.2

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests typesense && \
    curl -fsSL -o /tmp/typesense-server.tar.gz \
        https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz && \
    tar -xzf /tmp/typesense-server.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/typesense-join

# Fixed, non-secret demo API key shared by the task runtime and verifier for this
# fully self-contained, single-node Typesense setup.
ENV TYPESENSE_API_KEY=xyz

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense v30.2 standalone binary environment for a many-to-many JOINs task with asynchronous reference resolution."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - verifier/SDK pip3 packages: requests, typesense (Python SDK)
#   - Typesense server v30.2 standalone Linux binary installed at /usr/local/bin/typesense-server
#     (v30.2 is used because async_reference reference fields require Typesense v28.0+)
#   - /home/user/typesense-join: working directory for the task

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
