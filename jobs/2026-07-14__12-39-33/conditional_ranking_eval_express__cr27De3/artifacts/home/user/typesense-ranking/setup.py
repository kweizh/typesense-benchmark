"""
setup.py — Typesense catalog bootstrap
======================================
* Starts typesense-server (if not already running) on port 8108 with api-key=xyz.
* Waits until /health reports {"ok":true}.
* Drops the `catalog` collection if it exists, recreates it, imports all 6 docs.

Safe to re-run; the collection is always dropped and rebuilt from scratch.
"""

import subprocess
import sys
import time
import os
import json
import urllib.request
import urllib.error

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY      = "xyz"
HOST         = "http://localhost:8108"
DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SERVER_BIN   = "/usr/local/bin/typesense-server"
LOG_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "typesense.log")
COLLECTION   = "catalog"

HEADERS = {
    "Content-Type": "application/json",
    "X-TYPESENSE-API-KEY": API_KEY,
}

# ── Dataset ───────────────────────────────────────────────────────────────────
DOCUMENTS = [
    {"id": "P1", "title": "Alpine Trek Boots",   "description": "Alpine Trek ready footwear",      "badge": "featured",  "popularity": 10},
    {"id": "P2", "title": "Alpine Trek Jacket",  "description": "Alpine Trek insulated layer",     "badge": "featured",  "popularity": 80},
    {"id": "P3", "title": "Alpine Trek Poles",   "description": "Summit carbon poles",             "badge": "sponsored", "popularity": 5},
    {"id": "P4", "title": "Alpine Trek Tent",    "description": "Alpine Trek shelter system",      "badge": "none",      "popularity": 99},
    {"id": "P5", "title": "Alpine Trek Gloves",  "description": "Summit winter gloves",            "badge": "sponsored", "popularity": 40},
    {"id": "P6", "title": "Alpine Trek Socks",   "description": "Merino wool socks",               "badge": "featured",  "popularity": 100},
]

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = {
    "name": COLLECTION,
    "fields": [
        {"name": "id",          "type": "string"},
        {"name": "title",       "type": "string"},
        {"name": "description", "type": "string"},
        {"name": "badge",       "type": "string", "facet": True},
        {"name": "popularity",  "type": "int32"},
    ],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _request(method: str, path: str, body=None) -> dict:
    url  = HOST + path
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        return json.loads(text) if text else {}


def _start_server() -> None:
    """Launch typesense-server as a background process if not yet healthy."""
    # Already healthy? Nothing to do.
    if _is_healthy():
        print("[setup] Server already running — skipping launch.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    log_fh = open(LOG_FILE, "a")
    cmd = [
        SERVER_BIN,
        f"--data-dir={DATA_DIR}",
        f"--api-key={API_KEY}",
        "--api-port=8108",
        "--enable-cors=true",
    ]
    print(f"[setup] Starting typesense-server …  (log → {LOG_FILE})")
    subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh, start_new_session=True)


def _is_healthy() -> bool:
    try:
        with urllib.request.urlopen(HOST + "/health", timeout=2) as r:
            return json.loads(r.read()).get("ok") is True
    except Exception:
        return False


def _wait_healthy(timeout: int = 30) -> None:
    print("[setup] Waiting for /health …", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_healthy():
            print(" ready.")
            return
        print(".", end="", flush=True)
        time.sleep(0.5)
    print()
    sys.exit("[setup] ERROR: server did not become healthy in time.")


def _drop_collection() -> None:
    result = _request("DELETE", f"/collections/{COLLECTION}")
    if "name" in result:
        print(f"[setup] Dropped existing collection '{COLLECTION}'.")
    elif result.get("message", "").lower().startswith("not found"):
        print(f"[setup] Collection '{COLLECTION}' did not exist — skipping drop.")


def _create_collection() -> None:
    result = _request("POST", "/collections", SCHEMA)
    if result.get("name") == COLLECTION:
        print(f"[setup] Created collection '{COLLECTION}'.")
    else:
        sys.exit(f"[setup] ERROR creating collection: {result}")


def _import_documents() -> None:
    # Typesense bulk-import expects newline-delimited JSON.
    ndjson = "\n".join(json.dumps(d) for d in DOCUMENTS).encode()
    url    = f"{HOST}/collections/{COLLECTION}/documents/import?action=create"
    req    = urllib.request.Request(url, data=ndjson, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req) as resp:
        lines = resp.read().decode().strip().splitlines()

    errors = [l for l in lines if not json.loads(l).get("success")]
    if errors:
        sys.exit(f"[setup] Import errors: {errors}")
    print(f"[setup] Imported {len(lines)} documents.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _start_server()
    _wait_healthy()
    _drop_collection()
    _create_collection()
    _import_documents()
    print("[setup] Done.")


if __name__ == "__main__":
    main()
