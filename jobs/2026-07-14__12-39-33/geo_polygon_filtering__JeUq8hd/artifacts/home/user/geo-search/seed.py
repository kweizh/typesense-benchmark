#!/usr/bin/env python3
"""
Idempotent seed script: (re)creates and populates the 'hubs' Typesense collection.
"""

import os
import sys
import json
import urllib.request
import urllib.error

HOST = "http://localhost:8108"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "")
if not API_KEY:
    print("ERROR: TYPESENSE_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

COLLECTION_NAME = "hubs"

SCHEMA = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "id",       "type": "string"},
        {"name": "name",     "type": "string"},
        {"name": "status",   "type": "string", "facet": True},
        {"name": "location", "type": "geopoint"},
    ],
}

# Hub dataset: location is [latitude, longitude]
HUBS = [
    {"id": "h01", "name": "Alpha",   "status": "active",      "location": [37.78,  -122.42]},
    {"id": "h02", "name": "Bravo",   "status": "active",      "location": [37.79,  -122.42]},
    {"id": "h03", "name": "Charlie", "status": "active",      "location": [37.81,  -122.42]},
    {"id": "h04", "name": "Delta",   "status": "active",      "location": [37.78,  -122.46]},
    {"id": "h05", "name": "Echo",    "status": "active",      "location": [37.78,  -122.38]},
    {"id": "h06", "name": "Foxtrot", "status": "active",      "location": [37.73,  -122.42]},
    {"id": "h07", "name": "Golf",    "status": "active",      "location": [37.77,  -122.432]},
    {"id": "h08", "name": "Hotel",   "status": "active",      "location": [37.77,  -122.438]},
    {"id": "h09", "name": "India",   "status": "maintenance", "location": [37.775, -122.42]},
    {"id": "h10", "name": "Juliet",  "status": "maintenance", "location": [37.785, -122.415]},
]


def request(method, path, body=None):
    url = HOST + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    # Drop existing collection if it exists
    status, _ = request("DELETE", f"/collections/{COLLECTION_NAME}")
    if status == 200:
        print(f"Dropped existing collection '{COLLECTION_NAME}'.")
    elif status == 404:
        print(f"Collection '{COLLECTION_NAME}' does not exist yet; nothing to drop.")
    else:
        print(f"WARNING: Unexpected status {status} when deleting collection.")

    # Create the collection
    status, resp = request("POST", "/collections", SCHEMA)
    if status != 201:
        print(f"ERROR: Failed to create collection (HTTP {status}): {resp}", file=sys.stderr)
        sys.exit(1)
    print(f"Created collection '{COLLECTION_NAME}'.")

    # Bulk-import documents via the import endpoint (JSONL format)
    jsonl_body = "\n".join(json.dumps(h) for h in HUBS).encode()
    url = f"{HOST}/collections/{COLLECTION_NAME}/documents/import?action=create"
    req = urllib.request.Request(url, data=jsonl_body, headers=HEADERS, method="POST")
    req.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        print(f"ERROR: Import failed (HTTP {e.code}): {raw}", file=sys.stderr)
        sys.exit(1)

    # Each line of the response is a JSON result per document
    errors = []
    for line in raw.strip().splitlines():
        result = json.loads(line)
        if not result.get("success", False):
            errors.append(result)

    if errors:
        print(f"ERROR: Some documents failed to import: {errors}", file=sys.stderr)
        sys.exit(1)

    print(f"Successfully seeded {len(HUBS)} hubs into '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
