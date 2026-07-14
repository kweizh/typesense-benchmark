#!/usr/bin/env python3
"""
seed.py – (Re)create and populate the `hubs` collection in Typesense.

Idempotent: deletes the collection if it already exists, then recreates
and re-indexes the full hub dataset.
"""
import sys
import typesense

API_KEY = "xyz"  # fallback; normally supplied via env
import os

API_KEY = os.environ.get("TYPESENSE_API_KEY", API_KEY)
HOST = "localhost"
PORT = 8108
COLLECTION_NAME = "hubs"

# ---------------------------------------------------------------------------
# Hub dataset – each location is [latitude, longitude].
# ---------------------------------------------------------------------------
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


def get_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [{"host": HOST, "port": PORT, "protocol": "http"}],
            "api_key": API_KEY,
            "connection_timeout_seconds": 10,
        }
    )


def main() -> None:
    client = get_client()

    # Drop the collection if it already exists (idempotent recreate).
    try:
        client.collections[COLLECTION_NAME].delete()
        print(f"Deleted existing collection '{COLLECTION_NAME}'.")
    except typesense.exceptions.ObjectNotFound:
        pass
    except Exception as exc:  # pragma: no cover – defensive
        print(f"Warning while deleting collection: {exc}", file=sys.stderr)

    # Create the collection schema.
    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "name", "type": "string"},
            {"name": "status", "type": "string", "facet": True},
            {"name": "location", "type": "geopoint"},
        ],
    }
    client.collections.create(schema)
    print(f"Created collection '{COLLECTION_NAME}'.")

    # Index all hub documents.
    client.collections[COLLECTION_NAME].documents.import_(HUBS)
    print(f"Indexed {len(HUBS)} hub documents.")


if __name__ == "__main__":
    main()