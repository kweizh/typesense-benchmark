#!/usr/bin/env python3
"""Create the catalog collection and index all products from products.jsonl."""

import json
import typesense

CLIENT = typesense.Client({
    "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
    "api_key": "xyz",
    "connection_timeout_seconds": 10,
})

COLLECTION_SCHEMA = {
    "name": "catalog",
    "fields": [
        {"name": "id", "type": "string"},
        {"name": "name", "type": "string"},
        {"name": "brand", "type": "string"},
    ],
}

DATA_FILE = "/home/user/typo-tuning/products.jsonl"


def main():
    # Delete existing collection if present
    try:
        CLIENT.collections["catalog"].delete()
        print("Deleted existing catalog collection")
    except Exception:
        pass

    # Create collection
    CLIENT.collections.create(COLLECTION_SCHEMA)
    print("Created catalog collection")

    # Read and import documents
    docs = []
    with open(DATA_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))

    # Import documents
    result = CLIENT.collections["catalog"].documents.import_(docs)
    print(f"Imported {len(docs)} documents")
    # Check for failures
    if isinstance(result, list):
        for item in result:
            if not item.get("success", True):
                print(f"  FAILED: {item}")
    print("Done")


if __name__ == "__main__":
    main()