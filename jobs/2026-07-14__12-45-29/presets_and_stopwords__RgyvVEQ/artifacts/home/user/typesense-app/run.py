#!/usr/bin/env python3
"""Typesense search CLI for the library catalogue.

Commands:
  python3 run.py --setup                 # idempotent setup of server, collection, docs, stopwords, preset
  python3 run.py --q "<query>"           # search using only the library_default preset
  python3 run.py --q "<query>" --explicit  # search passing query_by / sort_by / stopwords explicitly

Both search modes print to stdout a single JSON object of the form:
  {"found": <int>, "hits": [<id>, <id>, ...]}
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
SERVER_LOG = os.path.join(PROJECT_DIR, "typesense.log")
SERVER_BIN = "/usr/local/bin/typesense-server"

COLLECTION_NAME = "library"
STOPWORDS_NAME = "en_stopwords"
PRESET_NAME = "library_default"

DOCUMENTS: List[Dict[str, Any]] = [
    {"id": "1", "title": "The Great Gatsby",            "author": "F Scott Fitzgerald", "points": 90},
    {"id": "2", "title": "The Wizard of Oz",            "author": "L Frank Baum",       "points": 70},
    {"id": "3", "title": "A Wizard of Earthsea",        "author": "Ursula K Le Guin",   "points": 85},
    {"id": "4", "title": "Harry Potter and the Sorcerers Stone", "author": "J K Rowling", "points": 95},
    {"id": "5", "title": "The Lord of the Rings",       "author": "J R R Tolkien",      "points": 99},
]

COLLECTION_SCHEMA: Dict[str, Any] = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "title",  "type": "string"},
        {"name": "author", "type": "string"},
        {"name": "points", "type": "int32"},
    ],
    "default_sorting_field": "points",
}

STOPWORDS_BODY: Dict[str, Any] = {
    "locale": "en",
    "stopwords": ["the", "a", "of", "and"],
}

PRESET_VALUE: Dict[str, Any] = {
    "query_by": "title,author",
    "sort_by": "points:desc",
    "stopwords": STOPWORDS_NAME,
}

REQUEST_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _api(method: str, path: str, **kwargs: Any) -> requests.Response:
    """Issue an HTTP request against the Typesense REST API."""
    url = f"{BASE_URL}{path}"
    headers = dict(HEADERS)
    extra_headers = kwargs.pop("headers", None)
    if extra_headers:
        headers.update(extra_headers)
    return requests.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)


def _is_already_exists(exc: requests.HTTPError) -> bool:
    """Return True if the HTTP error represents an idempotency-conflict (409)."""
    response = exc.response
    if response is None:
        return False
    if response.status_code == 409:
        return True
    try:
        body = response.json()
    except ValueError:
        return False
    message = str(body.get("message", "")).lower()
    return "already exists" in message


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def _server_healthy() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2.0)
        if r.status_code == 200:
            body = r.json()
            return body.get("ok") is True
    except requests.RequestException:
        return False
    return False


def _server_reachable() -> bool:
    """Return True if *something* answers on the Typesense port (even with an error)."""
    try:
        requests.get(f"{BASE_URL}/health", timeout=2.0)
        return True
    except requests.RequestException:
        return False


def _wait_for_server(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_healthy():
            return
        time.sleep(0.25)
    raise RuntimeError(f"Typesense server did not become healthy within {timeout}s")


def start_server() -> None:
    """Start the Typesense server in the background, if it isn't already running."""
    if _server_healthy():
        return

    if not os.path.exists(SERVER_BIN):
        raise FileNotFoundError(f"typesense-server binary not found at {SERVER_BIN}")

    os.makedirs(DATA_DIR, exist_ok=True)
    log_fp = open(SERVER_LOG, "ab")
    cmd = [
        SERVER_BIN,
        f"--data-dir={DATA_DIR}",
        f"--api-key={API_KEY}",
        f"--api-port={PORT}",
        "--listen-address=0.0.0.0",
        "--enable-cors",
    ]
    # Detach so the server keeps running after this Python process exits.
    subprocess.Popen(  # noqa: S603 - we just verified the binary exists
        cmd,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    _wait_for_server()


def ensure_server() -> None:
    """Make sure *some* Typesense server is reachable on the configured port.

    If something else is already listening (e.g. the user started it manually),
    trust it and don't start a second instance.
    """
    if _server_healthy():
        return
    if _server_reachable():
        # Something answered but is not healthy yet; wait briefly.
        _wait_for_server(timeout=10.0)
        return
    start_server()


# ---------------------------------------------------------------------------
# Setup operations (all idempotent)
# ---------------------------------------------------------------------------

def _create_collection() -> None:
    # GET first to skip POST when it already exists with the right schema.
    try:
        existing = _api("GET", f"/collections/{COLLECTION_NAME}")
        if existing.status_code == 200:
            return
    except requests.HTTPError:
        pass

    try:
        r = _api("POST", "/collections", json=COLLECTION_SCHEMA)
        r.raise_for_status()
    except requests.HTTPError as exc:
        if _is_already_exists(exc):
            return
        raise


def _index_documents() -> None:
    # POST as JSONL via the import endpoint; action=upsert keeps this idempotent.
    body = "\n".join(json.dumps(doc) for doc in DOCUMENTS) + "\n"
    r = _api(
        "POST",
        f"/collections/{COLLECTION_NAME}/documents/import?action=upsert",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    # The endpoint returns one JSON object per line; verify all succeeded.
    for line in r.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            outcome = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(outcome, dict) and outcome.get("success") is not True:
            raise RuntimeError(f"Document import line failed: {outcome}")


def _create_stopwords_set() -> None:
    # PUT /stopwords/<id> is idempotent: it upserts the named set.
    r = _api("PUT", f"/stopwords/{STOPWORDS_NAME}", json=STOPWORDS_BODY)
    r.raise_for_status()


def _create_preset() -> None:
    # PUT /presets/<name> is idempotent: it upserts the named preset.
    r = _api("PUT", f"/presets/{PRESET_NAME}", json={"value": PRESET_VALUE})
    r.raise_for_status()


def setup() -> None:
    start_server()
    _create_collection()
    _index_documents()
    _create_stopwords_set()
    _create_preset()
    print("setup complete")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _hits_to_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "found": int(payload.get("found", 0)),
        "hits": [hit["document"]["id"] for hit in payload.get("hits", [])],
    }


def search_with_preset(query: str) -> Dict[str, Any]:
    """Search driven entirely by the stored preset."""
    r = _api(
        "GET",
        f"/collections/{COLLECTION_NAME}/documents/search",
        params={"q": query, "preset": PRESET_NAME},
    )
    r.raise_for_status()
    return _hits_to_result(r.json())


def search_with_explicit(query: str) -> Dict[str, Any]:
    """Search driven by passing query_by / sort_by / stopwords explicitly."""
    params = {
        "q": query,
        "query_by": PRESET_VALUE["query_by"],
        "sort_by": PRESET_VALUE["sort_by"],
        "stopwords": PRESET_VALUE["stopwords"],
    }
    r = _api(
        "GET",
        f"/collections/{COLLECTION_NAME}/documents/search",
        params=params,
    )
    r.raise_for_status()
    return _hits_to_result(r.json())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Typesense-backed CLI for the library catalogue.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--setup",
        action="store_true",
        help="Start/ensure server and create collection, documents, stopwords set, and preset.",
    )
    group.add_argument(
        "--q",
        metavar="QUERY",
        help="Search the library collection. Use together with --explicit to bypass the preset.",
    )
    parser.add_argument(
        "--explicit",
        action="store_true",
        help="When used with --q, run the search with explicit parameters instead of the preset.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.setup:
        setup()
        return 0

    if args.q is not None:
        ensure_server()
        result = (
            search_with_explicit(args.q) if args.explicit else search_with_preset(args.q)
        )
        print(json.dumps(result, separators=(",", ":")))
        return 0

    return 2  # pragma: no cover - argparse's `required=True` prevents reaching here


if __name__ == "__main__":
    sys.exit(main())