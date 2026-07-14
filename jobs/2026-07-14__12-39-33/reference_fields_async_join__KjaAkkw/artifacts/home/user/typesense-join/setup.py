#!/usr/bin/env python3
"""
setup.py — Create collections and seed data for the users/products/likes demo.

Demonstrates asynchronous reference resolution in Typesense:
  • likes documents are indexed BEFORE their referenced users/products exist.
  • Once users/products are later indexed, Typesense resolves the references
    automatically (async_reference = True on both reference fields).
"""

import os
import sys
import time
import json
import requests

API_KEY  = os.environ.get("TYPESENSE_API_KEY", "xyz")
BASE_URL = "http://localhost:8108"
HEADERS  = {"X-TYPESENSE-API-KEY": API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_health(timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.ok and r.json().get("ok"):
                print("[health] Typesense is up.")
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.5)
    sys.exit("ERROR: Typesense did not become healthy in time.")


def delete_collection(name: str) -> None:
    r = requests.delete(f"{BASE_URL}/collections/{name}", headers=HEADERS)
    if r.status_code not in (200, 404):
        print(f"  WARN: DELETE /collections/{name} → {r.status_code} {r.text}")


def create_collection(schema: dict) -> dict:
    r = requests.post(f"{BASE_URL}/collections", headers=HEADERS, json=schema)
    r.raise_for_status()
    return r.json()


def index_document(collection: str, doc: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/collections/{collection}/documents",
        headers=HEADERS,
        json=doc,
    )
    if not r.ok:
        print(f"  WARN: index into {collection} → {r.status_code} {r.text}")
    return r.json()


def index_many(collection: str, docs: list[dict]) -> None:
    """Import a batch of documents (JSONL upsert)."""
    payload = "\n".join(json.dumps(d) for d in docs)
    r = requests.post(
        f"{BASE_URL}/collections/{collection}/documents/import",
        headers={**HEADERS, "Content-Type": "text/plain"},
        params={"action": "upsert"},
        data=payload.encode(),
    )
    r.raise_for_status()
    for line in r.text.splitlines():
        result = json.loads(line)
        if not result.get("success"):
            print(f"  WARN import into {collection}: {result}")


# ---------------------------------------------------------------------------
# Collection schemas
# ---------------------------------------------------------------------------

USERS_SCHEMA = {
    "name": "users",
    "fields": [
        {"name": "id",       "type": "string"},
        {"name": "username", "type": "string"},
    ],
}

PRODUCTS_SCHEMA = {
    "name": "products",
    "fields": [
        {"name": "id",           "type": "string"},
        {"name": "product_name", "type": "string"},
    ],
}

# The crucial schema: both reference fields carry async_reference=true so that
# a likes document can be indexed even when the referenced user/product doesn't
# exist yet. Typesense will resolve the join once they are indexed later.
LIKES_SCHEMA = {
    "name": "likes",
    "fields": [
        {"name": "id",         "type": "string"},
        {
            "name":            "user_id",
            "type":            "string",
            "reference":       "users.id",
            "async_reference": True,
        },
        {
            "name":            "product_id",
            "type":            "string",
            "reference":       "products.id",
            "async_reference": True,
        },
    ],
}


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

# Users and products that will be indexed *later* (after the likes that
# reference them, to prove async resolution works).
USERS = [
    {"id": "u1", "username": "alice"},
    {"id": "u2", "username": "bob"},
    {"id": "u3", "username": "carol"},
]

PRODUCTS = [
    {"id": "p1", "product_name": "Widget A"},
    {"id": "p2", "product_name": "Widget B"},
    {"id": "p3", "product_name": "Widget C"},
]

# Likes referencing users and products that do NOT exist yet at insert time.
# This is the key demonstration of async reference resolution.
LIKES_BEFORE_REFS = [
    {"id": "l1", "user_id": "u1", "product_id": "p1"},  # alice → Widget A
    {"id": "l2", "user_id": "u2", "product_id": "p1"},  # bob   → Widget A
    {"id": "l3", "user_id": "u1", "product_id": "p2"},  # alice → Widget B
]

# Additional likes that can be inserted *after* the referenced docs exist
# (normal path — just for extra coverage).
LIKES_AFTER_REFS = [
    {"id": "l4", "user_id": "u3", "product_id": "p2"},  # carol → Widget B
    {"id": "l5", "user_id": "u2", "product_id": "p3"},  # bob   → Widget C
    {"id": "l6", "user_id": "u3", "product_id": "p3"},  # carol → Widget C
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    wait_for_health()

    # ------------------------------------------------------------------
    # 1. (Re-)create all three collections
    # ------------------------------------------------------------------
    print("\n[setup] Dropping existing collections (if any)…")
    for name in ("likes", "users", "products"):   # order matters for FK deps
        delete_collection(name)

    print("[setup] Creating collections…")
    create_collection(USERS_SCHEMA)
    print("  ✓ users")
    create_collection(PRODUCTS_SCHEMA)
    print("  ✓ products")
    create_collection(LIKES_SCHEMA)
    print("  ✓ likes")

    # ------------------------------------------------------------------
    # 2. Index likes BEFORE the users/products they reference
    # ------------------------------------------------------------------
    print("\n[seed] Indexing likes BEFORE referenced users/products exist…")
    for like in LIKES_BEFORE_REFS:
        result = index_document("likes", like)
        print(f"  → like {like['id']}: {result}")

    # ------------------------------------------------------------------
    # 3. Now index the referenced users and products
    # ------------------------------------------------------------------
    print("\n[seed] Indexing users…")
    index_many("users", USERS)
    for u in USERS:
        print(f"  ✓ {u['id']} ({u['username']})")

    print("\n[seed] Indexing products…")
    index_many("products", PRODUCTS)
    for p in PRODUCTS:
        print(f"  ✓ {p['id']} ({p['product_name']})")

    # ------------------------------------------------------------------
    # 4. Index remaining likes (normal order, refs already exist)
    # ------------------------------------------------------------------
    print("\n[seed] Indexing remaining likes (refs exist now)…")
    for like in LIKES_AFTER_REFS:
        result = index_document("likes", like)
        print(f"  → like {like['id']}: {result}")

    # ------------------------------------------------------------------
    # 5. Quick sanity-check: verify join resolves for an early like
    # ------------------------------------------------------------------
    print("\n[verify] Sanity-checking join resolution for like l1 (u1→p1)…")
    time.sleep(0.5)   # give Typesense a moment to resolve async refs
    r = requests.get(
        f"{BASE_URL}/collections/likes/documents/l1",
        headers=HEADERS,
    )
    print(f"  like l1 raw doc: {r.json()}")

    print("\n[setup] Done. Run  python3 query.py --help  to query.\n")


if __name__ == "__main__":
    main()
