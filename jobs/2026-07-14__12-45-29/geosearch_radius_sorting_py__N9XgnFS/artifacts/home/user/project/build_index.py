#!/usr/bin/env python3
"""
Build (or rebuild) the `airports` Typesense collection.

Re-running this script MUST produce a clean, deterministic collection named
`airports` containing every record from `/home/user/project/data/airports.jsonl`.

The collection has a `location` field of type `geopoint`, which Typesense
expects as a [latitude, longitude] array (NOT GeoJSON's [lon, lat]).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Iterable

import typesense

COLLECTION_NAME = "airports"
DATASET_PATH = "/home/user/project/data/airports.jsonl"

# Schema: geopoint field MUST be called `location` (lat, lng order).
COLLECTION_SCHEMA: dict[str, Any] = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "id", "type": "string"},
        {"name": "name", "type": "string"},
        {"name": "iata", "type": "string"},
        {"name": "city", "type": "string", "optional": True},
        {"name": "country", "type": "string", "optional": True},
        {"name": "lat", "type": "float"},
        {"name": "lng", "type": "float"},
        {"name": "location", "type": "geopoint"},
    ],
    "default_sorting_field": "",
}


def make_client() -> typesense.Client:
    api_key = os.environ.get("TYPESENSE_API_KEY", "xyz")
    return typesense.Client(
        {
            "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
            "api_key": api_key,
            "connection_timeout_seconds": 5,
        }
    )


def reset_collection(client: typesense.Client) -> None:
    """Drop the collection if it exists, then create it fresh."""
    try:
        client.collections[COLLECTION_NAME].delete()
        print(f"Dropped existing collection '{COLLECTION_NAME}'.", file=sys.stderr)
    except typesense.exceptions.ObjectNotFound:
        pass
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Warning: could not drop collection: {exc}", file=sys.stderr)

    client.collections.create(COLLECTION_SCHEMA)
    print(f"Created collection '{COLLECTION_NAME}'.", file=sys.stderr)


def iter_airport_records(path: str) -> Iterable[str]:
    """Yield NDJSON-formatted airport records, one per line, with a
    `location` geopoint array derived from `lat`/`lng`."""
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            # Geopoint order is [latitude, longitude], not [lon, lat].
            obj["location"] = [float(obj["lat"]), float(obj["lng"])]
            yield json.dumps(obj, ensure_ascii=False)


def bulk_import(client: typesense.Client, path: str) -> int:
    documents = "\n".join(iter_airport_records(path))
    # `action: "create"` raises on duplicates; `action: "upsert"` would
    # overwrite. Since we just recreated the collection, plain "create"
    # is fine and surfaces bugs loudly.
    result = client.collections[COLLECTION_NAME].documents.import_(
        documents,
        {"action": "create"},
    )
    # The SDK returns a list of {"success": bool, ...} dicts when given a
    # raw NDJSON string; normalize to a count.
    if isinstance(result, str):
        result = [json.loads(line) for line in result.splitlines() if line]
    success = sum(1 for r in result if r.get("success"))
    failed = [r for r in result if not r.get("success")]
    if failed:
        print(f"{len(failed)} documents failed to import:", file=sys.stderr)
        for r in failed[:5]:
            print(f"  {r}", file=sys.stderr)
    return success


def main() -> int:
    client = make_client()
    reset_collection(client)
    imported = bulk_import(client, DATASET_PATH)
    print(f"Imported {imported} airports into '{COLLECTION_NAME}'.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
