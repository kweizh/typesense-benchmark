#!/usr/bin/env python3
"""Create the nested_orders collection and index all customer documents."""

import json
import os
import time

import requests

TYPESENSE_HOST = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION_NAME = "nested_orders"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "orders.jsonl")

HEADERS = {"X-TYPESENSE-API-KEY": API_KEY, "Content-Type": "application/json"}


def wait_for_server():
    for _ in range(30):
        try:
            r = requests.get(f"{TYPESENSE_HOST}/health", timeout=2)
            if r.status_code == 200 and r.json().get("ok"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Typesense server did not become healthy in time")


def delete_existing_collection():
    try:
        requests.delete(f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}", headers=HEADERS)
        print(f"Deleted existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass


def create_collection():
    schema = {
        "name": COLLECTION_NAME,
        "enable_nested_fields": True,
        "fields": [
            {"name": "id", "type": "string"},
            {"name": "customer_name", "type": "string"},
            # Nested fields: fields inside arrays of objects become array-typed.
            {"name": "orders.order_id", "type": "string[]", "optional": True},
            {"name": "orders.line_items.sku", "type": "string[]", "optional": True},
            {"name": "orders.line_items.name", "type": "string[]", "optional": True,
             "infix": True},
            {"name": "orders.line_items.category", "type": "string[]", "optional": True,
             "facet": True},
            {"name": "orders.line_items.price", "type": "float[]", "optional": True},
            {"name": "orders.line_items.attributes.color", "type": "string[]",
             "optional": True, "facet": True},
            {"name": "orders.line_items.attributes.material", "type": "string[]",
             "optional": True},
        ],
    }
    r = requests.post(f"{TYPESENSE_HOST}/collections", headers=HEADERS, json=schema)
    r.raise_for_status()
    print(f"Created collection '{COLLECTION_NAME}': {r.json()}")


def index_documents():
    documents = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            documents.append(json.loads(line))

    r = requests.post(
        f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}/documents/import?action=create",
        headers=HEADERS,
        data="\n".join(json.dumps(d) for d in documents),
    )
    r.raise_for_status()
    print(f"Indexed {len(documents)} documents.")

    # Verify count
    r = requests.get(f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}",
                     headers=HEADERS)
    r.raise_for_status()
    print(f"Collection now holds {r.json()['num_documents']} documents.")


def main():
    wait_for_server()
    delete_existing_collection()
    create_collection()
    index_documents()
    print("Setup complete.")


if __name__ == "__main__":
    main()