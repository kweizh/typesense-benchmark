#!/usr/bin/env python3
"""
Indexing step for the faceted-navigation backend.

Connects to a Typesense server running on localhost:8108 (api key "xyz"),
(re)creates the `products` collection with a schema that enables faceting on
`brand`, `category`, `tags` (string array) and `price`, then imports every
product from `data/products.jsonl`.

Running this script repeatedly leaves the collection in a clean, fully-indexed
state: any pre-existing `products` collection is deleted before re-creation.
"""

import json
import os
import sys

import typesense

TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = 8108
TYPESENSE_PROTOCOL = "http"
TYPESENSE_API_KEY = "xyz"

COLLECTION_NAME = "products"

# Resolve the dataset path relative to this script so the script works from any
# working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "products.jsonl")


def get_client() -> typesense.Client:
    return typesense.Client(
        {
            "api_key": TYPESENSE_API_KEY,
            "nodes": [
                {
                    "host": TYPESENSE_HOST,
                    "port": str(TYPESENSE_PORT),
                    "protocol": TYPESENSE_PROTOCOL,
                }
            ],
            "connection_timeout_seconds": 5,
        }
    )


def collection_exists(client: typesense.Client, name: str) -> bool:
    try:
        client.collections[name].retrieve()
        return True
    except Exception:
        return False


def load_products(path: str):
    """Yield product dicts parsed from the JSONL file."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> None:
    client = get_client()

    # (Re)create the collection so repeated runs leave a clean state.
    if collection_exists(client, COLLECTION_NAME):
        client.collections[COLLECTION_NAME].delete()
        print(f"Deleted existing collection '{COLLECTION_NAME}'.")

    schema = {
        "name": COLLECTION_NAME,
        # `id` is an implicit string field in Typesense; we don't need to
        # declare it explicitly.
        "fields": [
            {"name": "product_name", "type": "string"},
            {"name": "brand", "type": "string", "facet": True},
            {"name": "category", "type": "string", "facet": True},
            {"name": "tags", "type": "string[]", "facet": True},
            {"name": "price", "type": "float", "facet": True},
            {"name": "rating", "type": "float"},
        ],
        # No default sorting field; relevance / facet use is the priority here.
        "default_sorting_field": "",
    }

    client.collections.create(schema)
    print(f"Created collection '{COLLECTION_NAME}' with faceting schema.")

    # Load and import all products.
    products = list(load_products(DATA_PATH))
    if not products:
        print("WARNING: no products found in dataset.", file=sys.stderr)

    # The SDK's import_ accepts a list of dicts and returns per-document
    # import responses. We use the default return-id mode which is sufficient
    # to surface any import failures.
    import_responses = client.collections[COLLECTION_NAME].documents.import_(
        products
    )

    # Verify every document imported successfully.
    failures = [
        resp
        for resp in import_responses
        if not str(resp.get("success", "false")).lower() == "true"
    ]
    if failures:
        print(f"ERROR: {len(failures)} document(s) failed to import:", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        sys.exit(1)

    print(f"Imported {len(products)} product(s) into '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()