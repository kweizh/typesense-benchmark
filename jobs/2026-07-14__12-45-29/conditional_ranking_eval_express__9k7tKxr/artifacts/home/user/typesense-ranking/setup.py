#!/usr/bin/env python3
"""Setup script: (re)create the `catalog` collection in Typesense and index all 6 products.

Run with:  python3 setup.py

Behavior:
    * Waits for the Typesense server on http://localhost:8108 to report healthy.
    * Drops any existing `catalog` collection (so re-running is safe).
    * Creates the `catalog` collection with searchable title/description,
      a facetable/sortable/filterable `badge` and a sortable numeric `popularity`.
    * Indexes the 6 product documents listed in the spec.
"""

from __future__ import annotations

import os
import sys
import time

import typesense

# --- Configuration ---------------------------------------------------------
TYPESENSE_HOST = os.environ.get("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT = os.environ.get("TYPESENSE_PORT", "8108")
TYPESENSE_PROTOCOL = os.environ.get("TYPESENSE_PROTOCOL", "http")
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
COLLECTION_NAME = "catalog"

CATALOG_SCHEMA = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string"},
        # badge is used by the optional-filter / _eval expression,
        # so it must be indexed + filterable. It is also facetable/sortable.
        {"name": "badge", "type": "string", "facet": True, "index": True, "sort": True},
        # numeric tie-breaker; has to be indexable+sortable.
        {"name": "popularity", "type": "int32", "sort": True},
    ],
    "default_sorting_field": "popularity",
}

CATALOG_DOCUMENTS = [
    {"id": "P1", "title": "Alpine Trek Boots",  "description": "Alpine Trek ready footwear",  "badge": "featured",  "popularity": 10},
    {"id": "P2", "title": "Alpine Trek Jacket", "description": "Alpine Trek insulated layer", "badge": "featured",  "popularity": 80},
    {"id": "P3", "title": "Alpine Trek Poles",  "description": "Summit carbon poles",         "badge": "sponsored", "popularity": 5},
    {"id": "P4", "title": "Alpine Trek Tent",   "description": "Alpine Trek shelter system",  "badge": "none",      "popularity": 99},
    {"id": "P5", "title": "Alpine Trek Gloves", "description": "Summit winter gloves",        "badge": "sponsored", "popularity": 40},
    {"id": "P6", "title": "Alpine Trek Socks",  "description": "Merino wool socks",           "badge": "featured",  "popularity": 100},
]


def make_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [
                {"host": TYPESENSE_HOST, "port": TYPESENSE_PORT, "protocol": TYPESENSE_PROTOCOL}
            ],
            "api_key": TYPESENSE_API_KEY,
            "connection_timeout_seconds": 5,
        }
    )


def wait_for_server(client: typesense.Client, timeout: float = 30.0) -> None:
    """Poll the Typesense /health endpoint until the server reports ok=True.

    The official Typesense Python SDK exposes the health probe via
    `client.operations.is_healthy()`, which raises a connection error while
    the server is still starting and returns `True` once the cluster reports
    `{"ok": true}` to `GET /health`.
    """
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if client.operations.is_healthy():
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    msg = "Typesense server did not become healthy in time."
    if last_error is not None:
        msg += f" Last error: {last_error!r}"
    print(msg, file=sys.stderr)
    sys.exit(1)


def recreate_collection(client: typesense.Client) -> None:
    """Drop the collection if it exists, then create it from scratch."""
    try:
        client.collections[COLLECTION_NAME].delete()
        print(f"Dropped existing collection '{COLLECTION_NAME}'.")
    except typesense.exceptions.ObjectNotFound:
        # Not there yet - that is fine.
        pass
    except Exception as exc:  # pragma: no cover - surface other server-side errors
        print(f"While dropping collection: {exc}", file=sys.stderr)
        raise

    client.collections.create(CATALOG_SCHEMA)
    print(f"Created collection '{COLLECTION_NAME}' with schema.")


def index_documents(client: typesense.Client) -> None:
    result = client.collections[COLLECTION_NAME].documents.import_(
        CATALOG_DOCUMENTS, {"action": "upsert"}
    )
    failures = [r for r in result if not r.get("success", False)]
    if failures:
        print("Document import errors:", failures, file=sys.stderr)
        sys.exit(1)
    print(f"Indexed {len(CATALOG_DOCUMENTS)} documents in '{COLLECTION_NAME}'.")


def main() -> None:
    client = make_client()
    print(f"Waiting for Typesense at {TYPESENSE_PROTOCOL}://{TYPESENSE_HOST}:{TYPESENSE_PORT} ...")
    wait_for_server(client)
    recreate_collection(client)
    index_documents(client)
    print("Setup complete.")


if __name__ == "__main__":
    main()
