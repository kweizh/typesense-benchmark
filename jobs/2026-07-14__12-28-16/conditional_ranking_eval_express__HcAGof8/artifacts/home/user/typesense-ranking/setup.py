#!/usr/bin/env python3
"""
Setup script: (re)create and populate the `catalog` collection in Typesense.

Usage:
    python3 setup.py

This script is idempotent — safe to re-run. It drops the existing `catalog`
collection (if present), recreates it with the correct schema, and imports
all 6 product documents.
"""

import sys
import time
import requests

TYPESENSE_HOST = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION_NAME = "catalog"

HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

# Collection schema
SCHEMA = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string"},
        {"name": "badge", "type": "string", "facet": True},
        {"name": "popularity", "type": "int32"},
    ],
    "default_sorting_field": "popularity",
}

# Exact dataset to index
DOCUMENTS = [
    {"id": "P1", "title": "Alpine Trek Boots",  "description": "Alpine Trek ready footwear",  "badge": "featured",  "popularity": 10},
    {"id": "P2", "title": "Alpine Trek Jacket", "description": "Alpine Trek insulated layer", "badge": "featured",  "popularity": 80},
    {"id": "P3", "title": "Alpine Trek Poles",  "description": "Summit carbon poles",         "badge": "sponsored", "popularity": 5},
    {"id": "P4", "title": "Alpine Trek Tent",   "description": "Alpine Trek shelter system",  "badge": "none",      "popularity": 99},
    {"id": "P5", "title": "Alpine Trek Gloves", "description": "Summit winter gloves",       "badge": "sponsored", "popularity": 40},
    {"id": "P6", "title": "Alpine Trek Socks",  "description": "Merino wool socks",           "badge": "featured",  "popularity": 100},
]


def wait_for_server():
    """Wait until the Typesense server reports healthy."""
    for _ in range(30):
        try:
            r = requests.get(f"{TYPESENSE_HOST}/health", timeout=2)
            if r.ok and r.json().get("ok"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Typesense server did not become healthy in time")


def drop_collection():
    """Delete the collection if it already exists."""
    try:
        requests.delete(
            f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}",
            headers=HEADERS,
            timeout=10,
        )
    except Exception:
        pass  # Collection may not exist yet — that's fine


def create_collection():
    """Create the collection with the defined schema."""
    r = requests.post(
        f"{TYPESENSE_HOST}/collections",
        headers=HEADERS,
        json=SCHEMA,
        timeout=10,
    )
    r.raise_for_status()
    print(f"Collection '{COLLECTION_NAME}' created.")


def import_documents():
    """Import all documents into the collection (one at a time)."""
    for doc in DOCUMENTS:
        r = requests.post(
            f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}/documents?action=upsert",
            headers=HEADERS,
            json=doc,
            timeout=10,
        )
        if r.status_code not in (200, 201):
            print(f"Import error for {doc['id']} ({r.status_code}): {r.text}", file=sys.stderr)
            r.raise_for_status()
    print(f"Imported {len(DOCUMENTS)} documents.")


def main():
    wait_for_server()
    drop_collection()
    create_collection()
    import_documents()
    print("Setup complete.")


if __name__ == "__main__":
    main()