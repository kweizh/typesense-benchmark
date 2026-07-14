#!/usr/bin/env python3
"""
build_index.py – Create (or recreate) the Typesense 'airports' collection
and bulk-import every record from data/airports.jsonl.

Usage:
    TYPESENSE_API_KEY=xyz python3 build_index.py
"""

import json
import os
import sys

import typesense

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
COLLECTION_NAME = "airports"
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "airports.jsonl")

client = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": API_KEY,
        "connection_timeout_seconds": 10,
    }
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "id",      "type": "string"},
        {"name": "name",    "type": "string"},
        {"name": "iata",    "type": "string", "facet": False},
        {"name": "city",    "type": "string"},
        {"name": "country", "type": "string"},
        # geopoint field: stored as [latitude, longitude]
        {"name": "location", "type": "geopoint"},
    ],
}


def drop_collection_if_exists() -> None:
    try:
        client.collections[COLLECTION_NAME].retrieve()
        print(f"Collection '{COLLECTION_NAME}' already exists — dropping it.")
        client.collections[COLLECTION_NAME].delete()
        print(f"Collection '{COLLECTION_NAME}' dropped.")
    except typesense.exceptions.ObjectNotFound:
        pass  # nothing to drop


def create_collection() -> None:
    client.collections.create(SCHEMA)
    print(f"Collection '{COLLECTION_NAME}' created.")


def load_records() -> list[dict]:
    records = []
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            # Build the geopoint field from the flat lat/lng values.
            # Typesense expects [latitude, longitude] order.
            obj["location"] = [obj["lat"], obj["lng"]]
            records.append(obj)
    return records


def import_records(records: list[dict]) -> None:
    if not records:
        print("No records to import.")
        return

    # Bulk import using JSONL format
    jsonl_payload = "\n".join(json.dumps(r) for r in records)
    raw = client.collections[COLLECTION_NAME].documents.import_(
        jsonl_payload,
        {"action": "create"},
    )

    # The SDK returns a JSONL string; parse each line into a dict.
    results = [json.loads(line) for line in raw.splitlines() if line.strip()]
    errors = [r for r in results if not r.get("success", False)]
    if errors:
        print(f"WARNING: {len(errors)} document(s) failed to import:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
    else:
        print(f"Successfully imported {len(records)} airport record(s).")


def main() -> None:
    print(f"Data file : {DATA_FILE}")
    drop_collection_if_exists()
    create_collection()
    records = load_records()
    print(f"Records loaded from disk: {len(records)}")
    import_records(records)
    print("Done.")


if __name__ == "__main__":
    main()
