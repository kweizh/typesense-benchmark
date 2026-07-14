FROM ubuntu:24.04

ARG POCHI_VERSION
ARG TYPESENSE_VERSION=26.0

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests "typesense>=0.21,<1.0" && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the standalone Typesense server binary (native Linux amd64 release).
RUN curl -fsSL -o /tmp/typesense-server.tar.gz \
        "https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz" && \
    tar -xzf /tmp/typesense-server.tar.gz -C /usr/local/bin typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f /tmp/typesense-server.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Seed the multi-tenant project with a deterministic dataset (9 documents across
# 3 tenants: acme=3, globex=2, initech=4). Each document has a sensitive
# `secret_notes` field that scoped keys must hide from search responses.
RUN mkdir -p /home/user/typesense-task/data && \
    cat >/home/user/typesense-task/data/documents.jsonl <<'EOF'
{"id":"a1","tenant_id":"acme","title":"Quarterly Revenue Report","category":"finance","secret_notes":"acme internal margin 42%"}
{"id":"a2","tenant_id":"acme","title":"Product Launch Plan","category":"marketing","secret_notes":"acme launch budget 1.2M"}
{"id":"a3","tenant_id":"acme","title":"Engineering Roadmap","category":"engineering","secret_notes":"acme hiring 5 engineers"}
{"id":"g1","tenant_id":"globex","title":"Supply Chain Overview","category":"operations","secret_notes":"globex vendor list confidential"}
{"id":"g2","tenant_id":"globex","title":"Annual Budget Draft","category":"finance","secret_notes":"globex cost cuts 8%"}
{"id":"i1","tenant_id":"initech","title":"TPS Report Guidelines","category":"operations","secret_notes":"initech tps cover sheet required"}
{"id":"i2","tenant_id":"initech","title":"Office Relocation Memo","category":"hr","secret_notes":"initech new floor plan"}
{"id":"i3","tenant_id":"initech","title":"Software License Audit","category":"engineering","secret_notes":"initech unlicensed seats 12"}
{"id":"i4","tenant_id":"initech","title":"Customer Support Metrics","category":"support","secret_notes":"initech csat 91"}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense v26.0 standalone server with a multi-tenant dataset for scoped search API key isolation."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - requests + typesense (Python SDK) for task execution and verification
#   - /usr/local/bin/typesense-server: standalone Typesense v26.0 server binary
#   - /home/user/typesense-task: project directory
#   - /home/user/typesense-task/data/documents.jsonl: seeded multi-tenant dataset (9 docs across acme/globex/initech)

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
