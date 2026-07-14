#!/usr/bin/env python3
"""
setup.py — Idempotently provision Typesense collections and import sample data.

Usage:
    python3 setup.py

Environment:
    TYPESENSE_API_KEY   API key (default: xyz)
    TYPESENSE_HOST      Host (default: localhost)
    TYPESENSE_PORT      Port (default: 8108)
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HOST = os.environ.get("TYPESENSE_HOST", "localhost")
PORT = int(os.environ.get("TYPESENSE_PORT", "8108"))
BASE_URL = f"http://{HOST}:{PORT}"
DATA_DIR = Path(__file__).parent / "data"

HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Collection schemas
# ---------------------------------------------------------------------------
SCHEMAS = {
    "products": {
        "name": "products",
        "fields": [
            {"name": "id",           "type": "string"},
            {"name": "product_name", "type": "string"},
            {"name": "category",     "type": "string"},
            {"name": "price",        "type": "float"},
        ],
        "default_sorting_field": "price",
    },
    "articles": {
        "name": "articles",
        "fields": [
            {"name": "id",     "type": "string"},
            {"name": "title",  "type": "string"},
            {"name": "body",   "type": "string"},
            {"name": "author", "type": "string"},
        ],
    },
    "users": {
        "name": "users",
        "fields": [
            {"name": "id",        "type": "string"},
            {"name": "username",  "type": "string"},
            {"name": "full_name", "type": "string"},
            {"name": "bio",       "type": "string"},
        ],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: bytes | None = None) -> tuple[int, dict]:
    """Make an HTTP request and return (status_code, parsed_json)."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def collection_exists(name: str) -> bool:
    status, _ = _request("GET", f"/collections/{name}")
    return status == 200


def delete_collection(name: str) -> None:
    status, body = _request("DELETE", f"/collections/{name}")
    if status not in (200, 404):
        raise RuntimeError(f"Failed to delete collection '{name}': {body}")
    print(f"  Deleted existing collection '{name}'.")


def create_collection(schema: dict) -> None:
    name = schema["name"]
    payload = json.dumps(schema).encode()
    status, body = _request("POST", "/collections", body=payload)
    if status != 201:
        raise RuntimeError(f"Failed to create collection '{name}': {body}")
    print(f"  Created collection '{name}'.")


def import_documents(collection: str, jsonl_path: Path) -> None:
    """Bulk-import documents from a JSONL file using the import endpoint."""
    lines = jsonl_path.read_text().strip().splitlines()
    if not lines:
        print(f"  No documents found in {jsonl_path}.")
        return

    # Build newline-delimited JSONL payload
    payload = "\n".join(lines).encode()

    # Use action=upsert so re-running is idempotent
    url = f"{BASE_URL}/collections/{collection}/documents/import?action=upsert"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={**HEADERS, "Content-Type": "text/plain"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()

    # Each line of the response is a JSON result object
    results = [json.loads(line) for line in raw.strip().splitlines()]
    failures = [r for r in results if not r.get("success", False)]
    if failures:
        raise RuntimeError(
            f"Some documents failed to import into '{collection}': {failures}"
        )
    print(f"  Imported {len(results)} document(s) into '{collection}'.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Typesense Federated Search — Setup ===\n")

    for name, schema in SCHEMAS.items():
        print(f"[{name}]")

        # Drop and recreate so the schema is always current
        if collection_exists(name):
            delete_collection(name)

        create_collection(schema)

        jsonl_path = DATA_DIR / f"{name}.jsonl"
        if not jsonl_path.exists():
            print(f"  WARNING: data file '{jsonl_path}' not found — skipping import.")
        else:
            import_documents(name, jsonl_path)

        print()

    print("Setup complete.")


if __name__ == "__main__":
    main()
