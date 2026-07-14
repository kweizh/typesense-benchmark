#!/usr/bin/env python3
"""Index the product dataset into Typesense.

This script is idempotent: running it repeatedly leaves the ``products``
collection in a clean, fully-indexed state.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typesense


DATA_PATH = Path(__file__).parent / "data" / "products.jsonl"

CLIENT = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": "xyz",
        "connection_timeout_seconds": 30,
    }
)

COLLECTION_NAME = "products"

COLLECTION_SCHEMA = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "product_name", "type": "string"},
        {"name": "brand", "type": "string", "facet": True},
        {"name": "category", "type": "string", "facet": True},
        {"name": "tags", "type": "string[]", "facet": True},
        {"name": "price", "type": "float", "facet": True},
        {"name": "rating", "type": "float"},
    ],
    "default_sorting_field": "price",
}


def recreate_collection() -> None:
    """Delete and recreate the products collection with the desired schema."""
    try:
        CLIENT.collections[COLLECTION_NAME].delete()
        print(f"Deleted existing '{COLLECTION_NAME}' collection.")
    except typesense.exceptions.ObjectNotFound:
        print(f"No existing '{COLLECTION_NAME}' collection to delete.")
    except Exception as exc:  # noqa: BLE001 - surface any failure to the user
        print(f"Warning while deleting collection: {exc}", file=sys.stderr)

    CLIENT.collections.create(COLLECTION_SCHEMA)
    print(f"Created '{COLLECTION_NAME}' collection.")


def load_products() -> list[dict]:
    """Load every product from the JSONL dataset."""
    products: list[dict] = []
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            products.append(json.loads(line))
    return products


def import_products(products: list[dict]) -> None:
    """Import all products into Typesense in one batch."""
    if not products:
        print("Dataset is empty; nothing to import.")
        return

    result = CLIENT.collections[COLLECTION_NAME].documents.import_(
        products, {"action": "upsert"}
    )
    failures = [item for item in result if not item.get("success")]
    if failures:
        print(f"Failed to import {len(failures)} document(s):", file=sys.stderr)
        for failure in failures:
            print(json.dumps(failure), file=sys.stderr)
        sys.exit(1)
    print(f"Imported {len(products)} product(s).")


def main() -> None:
    if not DATA_PATH.exists():
        print(f"Dataset not found at {DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    recreate_collection()
    products = load_products()
    import_products(products)
    print("Indexing complete.")


if __name__ == "__main__":
    main()