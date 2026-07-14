FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep procps && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests pytest-xprocess typesense && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the standalone native Typesense server binary (v26.0, linux-amd64).
RUN cd /tmp && \
    curl -fsSL -O https://dl.typesense.org/releases/26.0/typesense-server-26.0-linux-amd64.tar.gz && \
    tar -xzf typesense-server-26.0-linux-amd64.tar.gz && \
    mv typesense-server /usr/local/bin/typesense-server && \
    chmod +x /usr/local/bin/typesense-server && \
    rm -f typesense-server-26.0-linux-amd64.tar.gz && \
    test -x /usr/local/bin/typesense-server

RUN mkdir -p /home/user && chmod 0755 /home/user

# Seed the airports dataset the executor must index. Coordinates are stored as
# separate lat/lng fields; the executor is responsible for building the geopoint.
# EDGE_IN (~99.9 km) and EDGE_OUT (~100.1 km) sit due north of CDG to exercise
# the exact-radius boundary at a 100 km radius.
RUN mkdir -p /home/user/project/data && \
    cat >/home/user/project/data/airports.jsonl <<'EOF'
{"id": "CDG", "name": "Paris Charles de Gaulle Airport", "iata": "CDG", "city": "Paris", "country": "France", "lat": 49.0097, "lng": 2.5479}
{"id": "LBG", "name": "Paris Le Bourget Airport", "iata": "LBG", "city": "Paris", "country": "France", "lat": 48.9694, "lng": 2.4414}
{"id": "ORY", "name": "Paris Orly Airport", "iata": "ORY", "city": "Paris", "country": "France", "lat": 48.7233, "lng": 2.3794}
{"id": "BVA", "name": "Beauvais-Tille Airport", "iata": "BVA", "city": "Beauvais", "country": "France", "lat": 49.4544, "lng": 2.1128}
{"id": "LIL", "name": "Lille Airport", "iata": "LIL", "city": "Lille", "country": "France", "lat": 50.5619, "lng": 3.0894}
{"id": "LHR", "name": "London Heathrow Airport", "iata": "LHR", "city": "London", "country": "United Kingdom", "lat": 51.4700, "lng": -0.4543}
{"id": "LGW", "name": "London Gatwick Airport", "iata": "LGW", "city": "London", "country": "United Kingdom", "lat": 51.1537, "lng": -0.1821}
{"id": "AMS", "name": "Amsterdam Airport Schiphol", "iata": "AMS", "city": "Amsterdam", "country": "Netherlands", "lat": 52.3105, "lng": 4.7683}
{"id": "BRU", "name": "Brussels Airport", "iata": "BRU", "city": "Brussels", "country": "Belgium", "lat": 50.9014, "lng": 4.4844}
{"id": "FRA", "name": "Frankfurt Airport", "iata": "FRA", "city": "Frankfurt", "country": "Germany", "lat": 50.0379, "lng": 8.5622}
{"id": "GVA", "name": "Geneva Airport", "iata": "GVA", "city": "Geneva", "country": "Switzerland", "lat": 46.2381, "lng": 6.1090}
{"id": "LYS", "name": "Lyon-Saint Exupery Airport", "iata": "LYS", "city": "Lyon", "country": "France", "lat": 45.7256, "lng": 5.0811}
{"id": "MRS", "name": "Marseille Provence Airport", "iata": "MRS", "city": "Marseille", "country": "France", "lat": 43.4393, "lng": 5.2214}
{"id": "NCE", "name": "Nice Cote d'Azur Airport", "iata": "NCE", "city": "Nice", "country": "France", "lat": 43.6584, "lng": 7.2159}
{"id": "TLS", "name": "Toulouse-Blagnac Airport", "iata": "TLS", "city": "Toulouse", "country": "France", "lat": 43.6293, "lng": 1.3638}
{"id": "BOD", "name": "Bordeaux-Merignac Airport", "iata": "BOD", "city": "Bordeaux", "country": "France", "lat": 44.8283, "lng": -0.7156}
{"id": "MAD", "name": "Adolfo Suarez Madrid-Barajas Airport", "iata": "MAD", "city": "Madrid", "country": "Spain", "lat": 40.4936, "lng": -3.5668}
{"id": "BCN", "name": "Barcelona-El Prat Airport", "iata": "BCN", "city": "Barcelona", "country": "Spain", "lat": 41.2974, "lng": 2.0833}
{"id": "EDGE_IN", "name": "Edge Marker Just Inside", "iata": "EIN", "city": "N/A", "country": "France", "lat": 49.90814, "lng": 2.5479}
{"id": "EDGE_OUT", "name": "Edge Marker Just Outside", "iata": "EOU", "city": "N/A", "country": "France", "lat": 49.90993, "lng": 2.5479}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="Typesense geosearch task: standalone typesense-server binary + Python SDK, with a seeded airports dataset in /home/user/project/data."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep (plus procps for pkill)
#   - always required pip3 packages: pytest-json-ctrf
#   - verification pip3 packages: requests, pytest-xprocess
#   - target library: typesense Python SDK (pip3) + standalone typesense-server v26.0 binary at /usr/local/bin/typesense-server
#   - /home/user/project: task project directory
#   - /home/user/project/data/airports.jsonl: seeded airport dataset (includes EDGE_IN / EDGE_OUT boundary markers)

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
