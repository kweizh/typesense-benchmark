#!/usr/bin/env python3
"""
index_data.py — (Re)create the 'products' Typesense collection and import all
products from data/products.jsonl.  Safe to run repeatedly; it drops and
recreates the collection each time so the state is always clean.
"""

import json
import os
import sys

import typesense

# ── Connection ──────────────────────────────────────────────────────────────
CLIENT = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": "xyz",
        "connection_timeout_seconds": 10,
    }
)

COLLECTION = "products"

SCHEMA = {
    "name": COLLECTION,
    "fields": [
        {"name": "product_name", "type": "string"},
        {"name": "brand",        "type": "string",  "facet": True},
        {"name": "category",     "type": "string",  "facet": True},
        {"name": "tags",         "type": "string[]", "facet": True},
        {"name": "price",        "type": "float",   "facet": True},
        {"name": "rating",       "type": "float"},
    ],
    "default_sorting_field": "rating",
    # Exact facet counts, not approximate
    "token_separators": [],
}


def recreate_collection() -> None:
    """Drop (if exists) and recreate the collection."""
    try:
        CLIENT.collections[COLLECTION].delete()
        print(f"Dropped existing collection '{COLLECTION}'.")
    except typesense.exceptions.ObjectNotFound:
        pass

    CLIENT.collections.create(SCHEMA)
    print(f"Created collection '{COLLECTION}'.")


def import_products(jsonl_path: str) -> None:
    """Read all products from *jsonl_path* and bulk-import them."""
    with open(jsonl_path, encoding="utf-8") as fh:
        documents = [json.loads(line) for line in fh if line.strip()]

    result = CLIENT.collections[COLLECTION].documents.import_(
        documents,
        {"action": "create"},
    )

    # result is a list of dicts with a 'success' key
    failures = [r for r in result if not r.get("success", False)]
    if failures:
        print(f"WARNING: {len(failures)} document(s) failed to import:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
    else:
        print(f"Imported {len(documents)} product(s) successfully.")


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = os.path.join(script_dir, "data", "products.jsonl")

    if not os.path.exists(jsonl_path):
        sys.exit(f"Dataset not found: {jsonl_path}")

    recreate_collection()
    import_products(jsonl_path)
    print("Done.")


if __name__ == "__main__":
    main()
