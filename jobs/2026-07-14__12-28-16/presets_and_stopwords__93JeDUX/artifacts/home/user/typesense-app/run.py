#!/usr/bin/env python3
"""
Typesense search backend: presets + stopwords.

Commands:
  python3 run.py --setup            Stand up server + collection + docs + stopwords + preset (idempotent)
  python3 run.py --q "<query>"     Search the `library` collection using ONLY the `library_default` preset
  python3 run.py --q "<query>" --explicit   Equivalent search passing query_by/sort_by/stopwords explicitly
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HOST = "localhost"
PORT = 8108
API_KEY = "xyz"
BASE_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{BASE_URL}/health"

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "typesense-data"
LOG_FILE = PROJECT_DIR / "typesense-server.log"
SERVER_BIN = "/usr/local/bin/typesense-server"

COLLECTION = "library"
STOPWORDS_ID = "en_stopwords"
PRESET_ID = "library_default"

DOCUMENTS = [
    {"id": "1", "title": "The Great Gatsby", "author": "F Scott Fitzgerald", "points": 90},
    {"id": "2", "title": "The Wizard of Oz", "author": "L Frank Baum", "points": 70},
    {"id": "3", "title": "A Wizard of Earthsea", "author": "Ursula K Le Guin", "points": 85},
    {"id": "4", "title": "Harry Potter and the Sorcerers Stone", "author": "J K Rowling", "points": 95},
    {"id": "5", "title": "The Lord of the Rings", "author": "J R R Tolkien", "points": 99},
]

# Shared search parameters. The preset stores exactly these so that the
# explicit path and the preset path are guaranteed to agree.
QUERY_BY = "title,author"
SORT_BY = "points:desc"
STOPWORDS = STOPWORDS_ID

TIMEOUT = httpx.Timeout(10.0, connect=2.0)


def headers():
    return {"X-TYPESENSE-API-KEY": API_KEY}


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------
def server_healthy() -> bool:
    try:
        r = httpx.get(HEALTH_URL, timeout=2.0)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


def ensure_server():
    if server_healthy():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.touch(exist_ok=True)

    cmd = [
        SERVER_BIN,
        f"--data-dir={DATA_DIR}",
        f"--api-key={API_KEY}",
        f"--listening-port={PORT}",
        "--enable-cors",
    ]
    with open(LOG_FILE, "ab") as logf:
        proc = subprocess.Popen(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach so it survives this process exiting
        )
    # record the pid for informational purposes
    (PROJECT_DIR / "typesense-server.pid").write_text(str(proc.pid))

    # wait for health
    for _ in range(60):
        if server_healthy():
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"Typesense server did not become healthy in time. See {LOG_FILE}."
    )


# ---------------------------------------------------------------------------
# Setup (idempotent)
# ---------------------------------------------------------------------------
def api_call(method, path, **kwargs):
    url = f"{BASE_URL}{path}"
    kwargs.setdefault("timeout", TIMEOUT)
    hdrs = headers()
    hdrs.update(kwargs.pop("headers", {}))
    r = httpx.request(method, url, headers=hdrs, **kwargs)
    return r


def setup():
    ensure_server()

    # Collection: drop if it exists, then recreate (keeps setup idempotent).
    r = api_call("DELETE", f"/collections/{COLLECTION}")
    # 404 is fine (didn't exist); anything else non-4xx also fine
    r = api_call(
        "POST",
        "/collections",
        json={
            "name": COLLECTION,
            "fields": [
                {"name": "title", "type": "string"},
                {"name": "author", "type": "string"},
                {"name": "points", "type": "int32"},
            ],
            "default_sorting_field": "points",
        },
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create collection: {r.status_code} {r.text}")

    # Index documents via the import endpoint with upsert action.
    import_lines = "\n".join(json.dumps(d) for d in DOCUMENTS)
    r = api_call(
        "POST",
        f"/collections/{COLLECTION}/documents?action=upsert",
        content=import_lines.encode("utf-8"),
        headers={**headers(), "Content-Type": "text/plain"},
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to index documents: {r.status_code} {r.text}")

    # Stopwords set: PUT /stopwords/:id (upsert).
    r = api_call(
        "PUT",
        f"/stopwords/{STOPWORDS_ID}",
        json={
            "locale": "en",
            "stopwords": ["the", "a", "of", "and"],
        },
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create stopwords set: {r.status_code} {r.text}")

    # Preset: PUT /presets/:name with a flat `value` object (single-collection).
    r = api_call(
        "PUT",
        f"/presets/{PRESET_ID}",
        json={
            "value": {
                "query_by": QUERY_BY,
                "sort_by": SORT_BY,
                "stopwords": STOPWORDS,
            }
        },
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create preset: {r.status_code} {r.text}")

    print("Setup complete.")
    print(f"  collection : {COLLECTION} ({len(DOCUMENTS)} documents)")
    print(f"  stopwords  : {STOPWORDS_ID}")
    print(f"  preset     : {PRESET_ID}")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search(q: str, explicit: bool):
    ensure_server()
    params = {"q": q}
    if explicit:
        params["query_by"] = QUERY_BY
        params["sort_by"] = SORT_BY
        params["stopwords"] = STOPWORDS
    else:
        params["preset"] = PRESET_ID

    r = api_call("GET", f"/collections/{COLLECTION}/documents/search", params=params)
    if r.status_code != 200:
        raise RuntimeError(f"Search failed: {r.status_code} {r.text}")

    data = r.json()
    found = data.get("found", 0)
    hits = [h["document"]["id"] for h in data.get("hits", [])]
    out = {"found": found, "hits": hits}
    print(json.dumps(out))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Typesense library search CLI")
    parser.add_argument("--setup", action="store_true", help="Set up server, collection, docs, stopwords, preset")
    parser.add_argument("--q", dest="query", default=None, help="Query text to search the library collection")
    parser.add_argument("--explicit", action="store_true", help="Pass parameters explicitly instead of using the preset")
    args = parser.parse_args()

    if args.setup:
        setup()
        return
    if args.query is not None:
        search(args.query, args.explicit)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()