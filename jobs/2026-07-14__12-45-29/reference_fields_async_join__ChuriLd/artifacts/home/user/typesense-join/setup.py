#!/usr/bin/env python3
"""Create the Typesense schema and seed data, ensuring that a `likes` document
is indexed BEFORE the user and the product it references, so that the
asynchronous reference resolution can be observed end-to-end."""

import os
import sys
import time

import typesense

API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HOST = "localhost"
PORT = "8108"
PROTOCOL = "http"

client = typesense.Client(
    {
        "nodes": [{"host": HOST, "port": PORT, "protocol": PROTOCOL}],
        "api_key": API_KEY,
        "connection_timeout_seconds": 10,
    }
)

ADMIN = client.collections


def delete_if_exists(name):
    try:
        ADMIN[name].delete()
    except typesense.exceptions.ObjectNotFound:
        pass
    except Exception as exc:  # pragma: no cover - cleanup best-effort
        print(f"[warn] could not delete {name}: {exc}", file=sys.stderr)
    # Give the server a moment to finalise deletion before recreating.
    time.sleep(0.3)


for name in ("users", "products", "likes"):
    delete_if_exists(name)

# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
print("Creating users collection...")
ADMIN.create(
    {
        "name": "users",
        "fields": [
            {"name": "username", "type": "string"},
        ],
    }
)

# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------
print("Creating products collection...")
ADMIN.create(
    {
        "name": "products",
        "fields": [
            {"name": "product_name", "type": "string"},
        ],
    }
)

# ---------------------------------------------------------------------------
# likes (linking collection) - asynchronous reference resolution on both sides
# ---------------------------------------------------------------------------
print("Creating likes collection with async reference fields...")
ADMIN.create(
    {
        "name": "likes",
        "fields": [
            {
                "name": "user_id",
                "type": "string",
                "reference": "users.id",
                "async_reference": True,
            },
            {
                "name": "product_id",
                "type": "string",
                "reference": "products.id",
                "async_reference": True,
            },
        ],
    }
)
time.sleep(0.5)

users_col = ADMIN["users"].documents
products_col = ADMIN["products"].documents
likes_col = ADMIN["likes"].documents

# ---------------------------------------------------------------------------
# Stage 1: a like for an as-yet-unindexed user + product
# ---------------------------------------------------------------------------
print("\n--- Stage 1: indexing a likes document that references NOT-YET-EXISTENT user and product ---")
likes_col.create(
    {
        "id": "like-1",
        "user_id": "u-future",
        "product_id": "p-future",
    }
)
print("Indexed like-1 -> user_id=u-future, product_id=p-future (both targets missing)")

# ---------------------------------------------------------------------------
# Stage 2: like that IS resolved immediately
# ---------------------------------------------------------------------------
print("\n--- Stage 2: indexing a normal user + product + like ---")
users_col.create({"id": "u-alice", "username": "alice"})
products_col.create({"id": "p-widget", "product_name": "Widget"})
likes_col.create({"id": "like-2", "user_id": "u-alice", "product_id": "p-widget"})
print("Indexed u-alice, p-widget and like-2 between them.")

# ---------------------------------------------------------------------------
# Stage 3: more users/products/likes
# ---------------------------------------------------------------------------
print("\n--- Stage 3: indexing additional users + products + likes ---")
users_batch = [
    {"id": "u-bob", "username": "bob"},
    {"id": "u-carol", "username": "carol"},
    {"id": "u-dave", "username": "dave"},
]
products_batch = [
    {"id": "p-gadget", "product_name": "Gadget"},
    {"id": "p-gizmo", "product_name": "Gizmo"},
]
likes_batch = [
    {"id": "like-3", "user_id": "u-bob", "product_id": "p-gadget"},
    {"id": "like-4", "user_id": "u-carol", "product_id": "p-gadget"},
    {"id": "like-5", "user_id": "u-carol", "product_id": "p-gizmo"},
    {"id": "like-6", "user_id": "u-dave", "product_id": "p-gizmo"},
    # duplicate (carol -> gadget) - exercises de-duplication in the CLI
    {"id": "like-7", "user_id": "u-carol", "product_id": "p-gadget"},
]
users_col.import_(users_batch, {"action": "create"})
products_col.import_(products_batch, {"action": "create"})
likes_col.import_(likes_batch, {"action": "create"})
print("Indexed additional users, products and likes.")

# ---------------------------------------------------------------------------
# Stage 4: NOW the missing referenced user and product are indexed. References
# in like-1 must resolve asynchronously.
# ---------------------------------------------------------------------------
print("\n--- Stage 4: indexing the previously-missing user and product ---")
users_col.create({"id": "u-future", "username": "future_user"})
products_col.create({"id": "p-future", "product_name": "Future_Product"})
likes_col.create({"id": "like-8", "user_id": "u-future", "product_id": "p-future"})
print("Indexed u-future and p-future.")

# Give the asynchronous reference resolution worker some time to propagate.
print("\nWaiting briefly for async reference resolution...")
time.sleep(2)

print("\nSetup complete.")
