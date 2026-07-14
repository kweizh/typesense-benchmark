#!/usr/bin/env python3
"""Provision the Typesense search engine for federated search.

Idempotently (re)creates the three collections (`products`, `articles`,
`users`) with schemas that match the provided JSONL sample data, then imports
the records into them. Running this script more than once will succeed and leave
the collections fully populated.
"""

import json
import os
import sys
import urllib.error
import urllib.request

TYPESENSE_HOST = os.environ.get("TYPESENSE_HOST", "http://localhost:8108")
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Schema for each collection. The `id` field is implicit in Typesense (a string
# primary key) and does not need to be declared, but every other field must be.
# Only the relevant text fields are marked as faceted/searchable; the per-query
# `query_by` used in search.py picks which of these fields to actually search.
SCHEMAS = {
    "products": {
        "name": "products",
        "default_sorting_field": "",
        "fields": [
            {"name": "product_name", "type": "string"},
            {"name": "category", "type": "string", "facet": True},
            {"name": "price", "type": "float"},
        ],
    },
    "articles": {
        "name": "articles",
        "default_sorting_field": "",
        "fields": [
            {"name": "title", "type": "string"},
            {"name": "body", "type": "string"},
            {"name": "author", "type": "string", "facet": True},
        ],
    },
    "users": {
        "name": "users",
        "default_sorting_field": "",
        "fields": [
            {"name": "username", "type": "string"},
            {"name": "full_name", "type": "string"},
            {"name": "bio", "type": "string"},
        ],
    },
}

# Mapping from collection name to the JSONL file that holds its records.
DATA_FILES = {
    "products": "products.jsonl",
    "articles": "articles.jsonl",
    "users": "users.jsonl",
}


def request(method, path, body=None, raw=False):
    """Perform an authenticated request against Typesense and return JSON."""
    url = f"{TYPESENSE_HOST}{path}"
    data = None
    headers = {
        "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
        "Accept": "application/json",
    }
    if body is not None:
        if raw:
            data = body.encode("utf-8") if isinstance(body, str) else body
            headers["Content-Type"] = "application/x-ndjson"
        else:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, _parse_payload(payload)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return exc.code, _parse_payload(payload)


def _parse_payload(payload):
    """Parse a JSON or NDJSON (one object per line) response body."""
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except ValueError:
        # The import endpoint returns NDJSON: one result object per line.
        items = []
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except ValueError:
                items.append({"error": line})
        return items if items else {"error": payload}


def drop_collection(name):
    """Delete a collection if it exists so re-runs start from a clean slate."""
    status, _ = request("DELETE", f"/collections/{name}")
    if status == 404:
        print(f"  collection '{name}' did not exist; skipping drop.")
    elif 200 <= status < 300:
        print(f"  dropped existing collection '{name}'.")
    else:
        print(f"  warning: could not drop '{name}' (status {status}).")


def create_collection(schema):
    status, body = request("POST", "/collections", schema)
    if status != 201:
        raise RuntimeError(f"failed to create collection '{schema['name']}': {body}")
    print(f"  created collection '{schema['name']}' with {len(schema['fields'])} fields.")


def import_records(name):
    """Import JSONL records into a collection using upsert (idempotent)."""
    path = os.path.join(DATA_DIR, DATA_FILES[name])
    with open(path, "r", encoding="utf-8") as fh:
        lines = [line.strip() for line in fh if line.strip()]
    ndjson = "\n".join(lines) + "\n"

    # action=upsert so re-runs update existing records by id instead of failing.
    # The bulk import endpoint is /documents/import and accepts NDJSON bodies.
    status, body = request("POST", f"/collections/{name}/documents/import?action=upsert", ndjson, raw=True)
    if status != 200:
        raise RuntimeError(f"failed to import into '{name}': {body}")

    # Typesense returns one JSON object per line in the import response.
    success = 0
    if isinstance(body, list):
        success = sum(1 for item in body if not isinstance(item, dict) or "success" not in item or item["success"])
    else:
        success = len(lines)
    print(f"  imported {success} record(s) into '{name}'.")


def main():
    print("Provisioning Typesense for federated search...")
    for name in SCHEMAS:
        drop_collection(name)
        create_collection(SCHEMAS[name])
        import_records(name)
    print("Done. Collections are ready for federated multi_search.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level guard for CLI script
        print(f"setup.py: error: {exc}", file=sys.stderr)
        sys.exit(1)