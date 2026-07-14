#!/usr/bin/env python3
"""Seed the `hubs` collection in the local Typesense instance.

Idempotent: drops and recreates the `hubs` collection, then loads the full
hub dataset defined in the task spec. Each hub's `location` is stored as a
geopoint in `[latitude, longitude]` order.
"""

from __future__ import annotations

import json
import os
import sys

import typesense
import typesense.exceptions


API_KEY = os.environ.get("TYPESENSE_API_KEY")
if not API_KEY:
    print("ERROR: TYPESENSE_API_KEY environment variable must be set", file=sys.stderr)
    sys.exit(1)

COLLECTION_NAME = "hubs"

# Authoritative dataset. Coordinates are [latitude, longitude] in that order.
HUBS = [
    {"id": "h01", "name": "Alpha",   "status": "active",      "latitude": 37.780, "longitude": -122.420},
    {"id": "h02", "name": "Bravo",   "status": "active",      "latitude": 37.790, "longitude": -122.420},
    {"id": "h03", "name": "Charlie", "status": "active",      "latitude": 37.810, "longitude": -122.420},
    {"id": "h04", "name": "Delta",   "status": "active",      "latitude": 37.780, "longitude": -122.460},
    {"id": "h05", "name": "Echo",    "status": "active",      "latitude": 37.780, "longitude": -122.380},
    {"id": "h06", "name": "Foxtrot", "status": "active",      "latitude": 37.730, "longitude": -122.420},
    {"id": "h07", "name": "Golf",    "status": "active",      "latitude": 37.770, "longitude": -122.432},
    {"id": "h08", "name": "Hotel",   "status": "active",      "latitude": 37.770, "longitude": -122.438},
    {"id": "h09", "name": "India",   "status": "maintenance", "latitude": 37.775, "longitude": -122.420},
    {"id": "h10", "name": "Juliet",  "status": "maintenance", "latitude": 37.785, "longitude": -122.415},
]


def main() -> int:
    client = typesense.Client(
        {
            "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
            "api_key": API_KEY,
            "connection_timeout_seconds": 5,
        }
    )

    # Drop the collection if it exists, then recreate it. This makes seeding
    # idempotent: re-running the script always leaves the collection in a
    # known, fully-populated state.
    try:
        client.collections[COLLECTION_NAME].delete()
    except typesense.exceptions.ObjectNotFound:
        pass

    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "name", "type": "string"},
            {"name": "status", "type": "string", "facet": True},
            {
                "name": "location",
                "type": "geopoint",
            },
        ],
    }
    client.collections.create(schema)

    documents = [
        {
            "id": hub["id"],
            "name": hub["name"],
            "status": hub["status"],
            # geopoint values must be [lat, lng] in that exact order.
            "location": [hub["latitude"], hub["longitude"]],
        }
        for hub in HUBS
    ]

    # The collection was just created empty, so the default `create` action
    # is sufficient and keeps the seed idempotent. (We drop+recreate up
    # top, so existing documents from a previous run are gone.) The
    # Typesense Python client v0.21 only validates `action` server-side
    # against {create, update, upsert}, which is why we use `create` here
    # rather than the deprecated `replace`.
    result = client.collections[COLLECTION_NAME].documents.import_(
        documents, {"action": "create"}
    )
    # import_ returns a per-document summary; fail if any document failed.
    failures = [entry for entry in result if not entry.get("success")]
    if failures:
        print(f"ERROR: failed to import {len(failures)} document(s):", file=sys.stderr)
        print(json.dumps(failures, indent=2), file=sys.stderr)
        return 1

    # Wait for indexing to finish so the search step sees all 10 hubs.
    # The Python client v0.21 doesn't expose wait_for_sync, so we poll the
    # collection metadata until the document count matches what we just
    # imported.
    expected_count = len(documents)
    import time
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        info = client.collections[COLLECTION_NAME].retrieve()
        if info.get("num_documents") == expected_count:
            break
        time.sleep(0.25)
    else:
        print(
            f"ERROR: only {info.get('num_documents')}/{expected_count} hubs indexed "
            "within 30s",
            file=sys.stderr,
        )
        return 1

    summary = {
        "collection": COLLECTION_NAME,
        "hubs_indexed": len(documents),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
