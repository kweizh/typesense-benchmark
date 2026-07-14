#!/usr/bin/env python3
"""
Typesense search app for the 'library' collection.

Usage:
  python3 run.py --setup                        # start server, create collection, index docs, register preset & stopwords
  python3 run.py --q "<query>"                  # search via library_default preset
  python3 run.py --q "<query>" --explicit       # search with explicit parameters (no preset)
"""

import argparse
import json
import os
import subprocess
import sys
import time

import urllib.request
import urllib.error

# ── Configuration ────────────────────────────────────────────────────────────
TYPESENSE_API_KEY  = "xyz"
TYPESENSE_HOST     = "http://localhost:8108"
TYPESENSE_BIN      = "/usr/local/bin/typesense-server"
DATA_DIR           = "/home/user/typesense-app/data"
LOG_FILE           = "/home/user/typesense-app/typesense.log"

COLLECTION_NAME    = "library"
PRESET_NAME        = "library_default"
STOPWORDS_SET_NAME = "en_stopwords"

HEADERS = {
    "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
    "Content-Type": "application/json",
}

# ── Documents ─────────────────────────────────────────────────────────────────
DOCUMENTS = [
    {"id": "1", "title": "The Great Gatsby",                       "author": "F Scott Fitzgerald", "points": 90},
    {"id": "2", "title": "The Wizard of Oz",                       "author": "L Frank Baum",       "points": 70},
    {"id": "3", "title": "A Wizard of Earthsea",                   "author": "Ursula K Le Guin",   "points": 85},
    {"id": "4", "title": "Harry Potter and the Sorcerers Stone",   "author": "J K Rowling",        "points": 95},
    {"id": "5", "title": "The Lord of the Rings",                  "author": "J R R Tolkien",      "points": 99},
]

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method: str, path: str, body=None):
    """Make an HTTP request to the Typesense server; return (status_code, parsed_json)."""
    url = TYPESENSE_HOST + path
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _get(path):
    return _request("GET", path)


def _post(path, body):
    return _request("POST", path, body)


def _put(path, body):
    return _request("PUT", path, body)


def _delete(path):
    return _request("DELETE", path)

# ── Server lifecycle ──────────────────────────────────────────────────────────

def _server_healthy() -> bool:
    try:
        status, body = _get("/health")
        return status == 200 and body.get("ok") is True
    except Exception:
        return False


def ensure_server_running():
    if _server_healthy():
        print("[server] Typesense is already running and healthy.")
        return

    print("[server] Starting Typesense server …")
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(LOG_FILE, "a") as log_fh:
        subprocess.Popen(
            [
                TYPESENSE_BIN,
                f"--data-dir={DATA_DIR}",
                f"--api-key={TYPESENSE_API_KEY}",
                "--api-port=8108",
                "--enable-cors=true",
            ],
            stdout=log_fh,
            stderr=log_fh,
            start_new_session=True,
        )

    # Wait up to 30 s for the server to become healthy
    for i in range(30):
        time.sleep(1)
        if _server_healthy():
            print(f"[server] Server healthy after {i + 1}s.")
            return

    sys.exit("[server] ERROR: Typesense did not become healthy within 30 seconds.")

# ── Collection ────────────────────────────────────────────────────────────────

def ensure_collection():
    status, body = _get(f"/collections/{COLLECTION_NAME}")
    if status == 200:
        print(f"[collection] '{COLLECTION_NAME}' already exists – skipping creation.")
        return

    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "title",  "type": "string"},
            {"name": "author", "type": "string"},
            {"name": "points", "type": "int32"},
        ],
        "default_sorting_field": "points",
    }
    status, body = _post("/collections", schema)
    if status == 201:
        print(f"[collection] Created '{COLLECTION_NAME}'.")
    else:
        sys.exit(f"[collection] ERROR creating collection: {status} {body}")

# ── Documents ─────────────────────────────────────────────────────────────────

def ensure_documents():
    # Use import with action=upsert so re-runs are safe
    ndjson = "\n".join(json.dumps(doc) for doc in DOCUMENTS)
    url    = TYPESENSE_HOST + f"/collections/{COLLECTION_NAME}/documents/import?action=upsert"
    data   = ndjson.encode()
    req    = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    # Override content-type for NDJSON import
    req.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(req) as resp:
            results = resp.read().decode().strip().splitlines()
    except urllib.error.HTTPError as exc:
        sys.exit(f"[documents] ERROR importing: {exc.code} {exc.read()}")

    errors = [r for r in results if '"success":false' in r]
    if errors:
        sys.exit(f"[documents] Import errors: {errors}")
    print(f"[documents] Upserted {len(results)} document(s) into '{COLLECTION_NAME}'.")

# ── Stopwords ─────────────────────────────────────────────────────────────────

def ensure_stopwords():
    status, body = _get(f"/stopwords/{STOPWORDS_SET_NAME}")
    if status == 200:
        print(f"[stopwords] Set '{STOPWORDS_SET_NAME}' already exists – skipping creation.")
        return

    payload = {
        "stopwords": ["the", "a", "of", "and"],
        "locale": "en",
    }
    status, body = _put(f"/stopwords/{STOPWORDS_SET_NAME}", payload)
    if status == 200:
        print(f"[stopwords] Created set '{STOPWORDS_SET_NAME}'.")
    else:
        sys.exit(f"[stopwords] ERROR creating stopwords set: {status} {body}")

# ── Preset ────────────────────────────────────────────────────────────────────

def ensure_preset():
    status, body = _get(f"/presets/{PRESET_NAME}")
    if status == 200:
        print(f"[preset] '{PRESET_NAME}' already exists – skipping creation.")
        return

    # The preset value must be a flat object of search parameters (not a
    # multi-search array) so it works with the single-collection search endpoint.
    payload = {
        "value": {
            "query_by":  "title,author",
            "sort_by":   "points:desc",
            "stopwords": STOPWORDS_SET_NAME,
        }
    }
    status, body = _put(f"/presets/{PRESET_NAME}", payload)
    if status == 200:
        print(f"[preset] Created preset '{PRESET_NAME}'.")
    else:
        sys.exit(f"[preset] ERROR creating preset: {status} {body}")

# ── Search ────────────────────────────────────────────────────────────────────

def _format_results(body: dict) -> dict:
    found = body.get("found", 0)
    hits  = [hit["document"]["id"] for hit in body.get("hits", [])]
    return {"found": found, "hits": hits}


def search_preset(query: str):
    """Search using only the library_default preset + q."""
    import urllib.parse
    params = urllib.parse.urlencode({"q": query, "preset": PRESET_NAME})
    status, body = _get(f"/collections/{COLLECTION_NAME}/documents/search?{params}")
    if status != 200:
        sys.exit(f"[search] ERROR: {status} {body}")
    return _format_results(body)


def search_explicit(query: str):
    """Search with explicit parameters — no preset reference."""
    import urllib.parse
    params = urllib.parse.urlencode({
        "q":         query,
        "query_by":  "title,author",
        "sort_by":   "points:desc",
        "stopwords": STOPWORDS_SET_NAME,
    })
    status, body = _get(f"/collections/{COLLECTION_NAME}/documents/search?{params}")
    if status != 200:
        sys.exit(f"[search] ERROR: {status} {body}")
    return _format_results(body)

# ── CLI entry-point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Typesense library search tool")
    parser.add_argument("--setup",    action="store_true", help="Start server and initialise the library collection")
    parser.add_argument("--q",        type=str,            help="Search query text")
    parser.add_argument("--explicit", action="store_true", help="Use explicit params instead of the preset")
    args = parser.parse_args()

    if args.setup:
        ensure_server_running()
        ensure_collection()
        ensure_documents()
        ensure_stopwords()
        ensure_preset()
        print("[setup] Done.")
        return

    if args.q is not None:
        # Ensure server is reachable before searching
        if not _server_healthy():
            sys.exit("[search] ERROR: Typesense server is not running. Run --setup first.")

        if args.explicit:
            result = search_explicit(args.q)
        else:
            result = search_preset(args.q)

        print(json.dumps(result))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
