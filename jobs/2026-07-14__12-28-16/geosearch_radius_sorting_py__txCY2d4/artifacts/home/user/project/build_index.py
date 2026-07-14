#!/usr/bin/env python3
"""Build (or rebuild) the `airports` Typesense collection from the JSONL dataset.

This script is idempotent: every run drops any existing `airports` collection
and recreates a clean one, then bulk-imports every record from
``data/airports.jsonl``.  The collection exposes a ``location`` field of
type ``geopoint`` so that geo radius filtering and distance sorting work.

Usage:
    python3 /home/user/project/build_index.py
"""

import json
import os
import sys

import typesense

# --- Configuration -----------------------------------------------------------

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(PROJECT_DIR, "data", "airports.jsonl")
COLLECTION_NAME = "airports"

TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = 8108
TYPESENSE_PROTOCOL = "http"
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")


def get_client() -> typesense.Client:
    """Return a configured Typesense client."""
    return typesense.Client(
        {
            "nodes": [
                {
                    "host": TYPESENSE_HOST,
                    "port": TYPESENSE_PORT,
                    "protocol": TYPESENSE_PROTOCOL,
                }
            ],
            "api_key": TYPESENSE_API_KEY,
            "connection_timeout_seconds": 10,
        }
    )


def load_records(path: str) -> list[dict]:
    """Read the JSONL dataset and convert each line to a Typesense document.

    Each source record has ``lat`` / ``lng`` numeric fields.  We add a
    ``location`` field as a ``[latitude, longitude]`` array (Typesense's
    geopoint convention -- note this is NOT GeoJSON's [lng, lat] order).
    """
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            doc = {
                "id": str(obj["id"]),
                "iata": str(obj["iata"]),
                "name": str(obj["name"]),
                "city": str(obj.get("city", "")),
                "country": str(obj.get("country", "")),
                # geopoint value: [latitude, longitude]
                "location": [float(obj["lat"]), float(obj["lng"])],
            }
            records.append(doc)
    return records


def drop_collection_if_exists(client: typesense.Client) -> None:
    """Delete the airports collection if it already exists (idempotent)."""
    try:
        client.collections[COLLECTION_NAME].delete()
        print(f"Deleted existing collection '{COLLECTION_NAME}'.")
    except typesense.exceptions.ObjectNotFound:
        # Collection did not exist -- nothing to drop.
        pass
    except typesense.exceptions.RequestException as exc:
        # Re-raise anything other than "not found".
        raise SystemExit(f"Unexpected error deleting collection: {exc}") from exc


def create_collection(client: typesense.Client) -> None:
    """Create the airports collection with a geopoint ``location`` field."""
    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "iata", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "city", "type": "string", "optional": True},
            {"name": "country", "type": "string", "optional": True},
            {"name": "location", "type": "geopoint"},
        ],
        "default_sorting_field": "",
    }
    client.collections.create(schema)
    print(f"Created collection '{COLLECTION_NAME}'.")


def bulk_import(client: typesense.Client, records: list[dict]) -> None:
    """Bulk-import records into the collection using the import endpoint."""
    import_results = client.collections[COLLECTION_NAME].documents.import_(
        records, {"action": "create"}
    )

    # The import endpoint returns one result entry per document.  Depending on
    # the SDK version / invocation style this can be:
    #   * a JSONLines string (or bytes),
    #   * a list of dicts,
    #   * a single dict.
    # Normalise to a list of result dicts.
    if isinstance(import_results, bytes):
        import_results = import_results.decode("utf-8")
    if isinstance(import_results, str):
        import_results = [
            json.loads(line)
            for line in import_results.strip().splitlines()
            if line.strip()
        ]
    elif isinstance(import_results, dict):
        import_results = [import_results]

    success = 0
    failures: list[str] = []
    for res in import_results:
        res_dict = res if isinstance(res, dict) else json.loads(res)
        if res_dict.get("success", False):
            success += 1
        else:
            failures.append(
                f"id={res_dict.get('id')}: "
                f"{res_dict.get('error', 'unknown error')}"
            )

    print(f"Imported {success} document(s) successfully.")
    if failures:
        for fmsg in failures:
            print(f"  FAILURE: {fmsg}", file=sys.stderr)
        raise SystemExit(f"{len(failures)} document(s) failed to import.")


def main() -> None:
    if not os.path.isfile(DATA_FILE):
        raise SystemExit(f"Dataset file not found: {DATA_FILE}")

    client = get_client()

    # 1. Drop existing collection (idempotent rebuild).
    drop_collection_if_exists(client)

    # 2. Create a fresh collection with a geopoint location field.
    create_collection(client)

    # 3. Load and bulk-import all records.
    records = load_records(DATA_FILE)
    print(f"Loaded {len(records)} record(s) from {DATA_FILE}.")
    bulk_import(client, records)

    print("Index build complete.")


if __name__ == "__main__":
    main()