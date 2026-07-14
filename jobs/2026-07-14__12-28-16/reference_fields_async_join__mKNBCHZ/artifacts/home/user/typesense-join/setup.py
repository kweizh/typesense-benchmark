#!/usr/bin/env python3
"""
Setup script for the Typesense many-to-many "likes" graph.

Creates three collections:
  - users    (field: username)
  - products (field: product_name)
  - likes    (reference fields: user_id -> users.id, product_id -> products.id,
              both with async_reference: true so a like can be indexed BEFORE
              the referenced user / product exists)

Seeds data so that at least one `likes` document is indexed BEFORE the user and
the product it references, then indexes those referenced documents afterwards
and verifies that the references resolve automatically.

This script is idempotent: it drops any existing collections and recreates them.
"""

import os
import sys
import time
import json

import typesense

TYPESENSE_HOST = os.environ.get("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT = int(os.environ.get("TYPESENSE_PORT", "8108"))
TYPESENSE_PROTOCOL = os.environ.get("TYPESENSE_PROTOCOL", "http")
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")


def get_client():
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


def wait_for_health():
    """Wait until the Typesense server reports healthy."""
    import urllib.request

    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f"http://{TYPESENSE_HOST}:{TYPESENSE_PORT}/health", timeout=3
            ) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok") is True:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    print("ERROR: Typesense server did not become healthy in time", file=sys.stderr)
    sys.exit(1)


def drop_collections(client):
    for name in ("likes", "products", "users"):
        try:
            client.collections[name].delete()
            print(f"  deleted existing collection '{name}'")
        except Exception:
            # collection did not exist
            pass


def create_collections(client):
    # Referenced collections must exist before the referencing one.
    users_schema = {
        "name": "users",
        "fields": [
            {"name": "username", "type": "string"},
        ],
    }
    products_schema = {
        "name": "products",
        "fields": [
            {"name": "product_name", "type": "string"},
        ],
    }
    likes_schema = {
        "name": "likes",
        "fields": [
            {
                "name": "user_id",
                "type": "string",
                "reference": "users.id",
                "optional": True,
                "async_reference": True,
            },
            {
                "name": "product_id",
                "type": "string",
                "reference": "products.id",
                "optional": True,
                "async_reference": True,
            },
        ],
    }

    client.collections.create(users_schema)
    print("  created collection 'users'")
    client.collections.create(products_schema)
    print("  created collection 'products'")
    client.collections.create(likes_schema)
    print("  created collection 'likes' (async reference fields)")


def index_doc(client, collection, doc):
    client.collections[collection].documents.create(doc)


def index_many(client, collection, docs):
    client.collections[collection].documents.import_(docs, {"action": "create"})


def seed_data(client):
    # ------------------------------------------------------------------
    # Step 1: Index a `likes` document BEFORE the referenced user and
    #         product exist. This is only possible thanks to
    #         async_reference: true on both reference fields.
    # ------------------------------------------------------------------
    early_like = {
        "id": "like_late",
        "user_id": "u_late",
        "product_id": "p_late",
    }
    index_doc(client, "likes", early_like)
    print(
        "  indexed likes/like_late referencing u_late & p_late "
        "(BEFORE those docs exist)"
    )

    # ------------------------------------------------------------------
    # Step 2: Index some users and products that the normal likes will
    #         reference (these exist before their likes).
    # ------------------------------------------------------------------
    users = [
        {"id": "u1", "username": "alice"},
        {"id": "u2", "username": "bob"},
    ]
    products = [
        {"id": "p1", "product_name": "Widget"},
        {"id": "p2", "product_name": "Gadget"},
    ]
    index_many(client, "users", users)
    index_many(client, "products", products)
    print("  indexed users u1, u2 and products p1, p2")

    # ------------------------------------------------------------------
    # Step 3: Index the normal likes (referenced docs already present).
    #         like_dup creates a duplicate (alice likes Widget twice) to
    #         exercise the de-duplication requirement of the CLI.
    # ------------------------------------------------------------------
    normal_likes = [
        {"id": "like1", "user_id": "u1", "product_id": "p1"},  # alice -> Widget
        {"id": "like2", "user_id": "u2", "product_id": "p1"},  # bob   -> Widget
        {"id": "like3", "user_id": "u1", "product_id": "p2"},  # alice -> Gadget
        {"id": "like_dup", "user_id": "u1", "product_id": "p1"},  # alice -> Widget (dup)
    ]
    index_many(client, "likes", normal_likes)
    print("  indexed normal likes (incl. a duplicate for de-dup testing)")

    # ------------------------------------------------------------------
    # Step 4: NOW index the user and product that like_late referenced
    #         earlier. The async references should resolve automatically.
    # ------------------------------------------------------------------
    index_doc(client, "users", {"id": "u_late", "username": "zoe"})
    index_doc(client, "products", {"id": "p_late", "product_name": "Thingamajig"})
    print("  indexed u_late (zoe) and p_late (Thingamajig) AFTER like_late")


def verify_resolution(client):
    """
    Confirm that the async references of like_late resolved after the
    referenced user/product were indexed.
    """
    print("\nVerifying async reference resolution for likes/like_late ...")
    resolved = False
    for _ in range(40):
        res = client.collections["likes"].documents.search(
            {
                "q": "*",
                "query_by": "",
                "filter_by": "id:=like_late",
                "include_fields": "$users(username),$products(product_name)",
                "per_page": 1,
            }
        )
        hits = res.get("hits", [])
        if hits:
            doc = hits[0]["document"]
            users_obj = doc.get("users")
            products_obj = doc.get("products")
            if users_obj and products_obj:
                username = users_obj.get("username")
                product_name = products_obj.get("product_name")
                if username and product_name:
                    print(
                        f"  RESOLVED: like_late -> user '{username}' "
                        f"(product '{product_name}')"
                    )
                    resolved = True
                    break
        time.sleep(0.25)

    if not resolved:
        print("  WARNING: references for like_late did not resolve in time")
        sys.exit(1)

    # Sanity: also confirm the normal join works for an early like.
    res = client.collections["likes"].documents.search(
        {
            "q": "*",
            "query_by": "",
            "filter_by": "product_id:=p1",
            "include_fields": "$users(username)",
            "per_page": 250,
        }
    )
    usernames = []
    for h in res.get("hits", []):
        u = h["document"].get("users")
        if u and u.get("username"):
            usernames.append(u["username"])
    print(f"  users who liked p1 (Widget) -> {sorted(set(usernames))}")


def main():
    print("Waiting for Typesense to be healthy ...")
    wait_for_health()
    print("Typesense is healthy.")

    client = get_client()

    print("Dropping any existing collections ...")
    drop_collections(client)

    print("Creating collections ...")
    create_collections(client)

    print("Seeding data ...")
    seed_data(client)

    verify_resolution(client)

    print("\nSetup complete.")
    print("Collections: users, products, likes")
    print(
        "Try:  python3 query.py --product p1        # ['alice', 'bob']"
    )
    print(
        "Try:  python3 query.py --product p_late   # ['zoe']"
    )
    print(
        "Try:  python3 query.py --user u1          # ['Gadget', 'Widget']"
    )
    print(
        "Try:  python3 query.py --user u_late      # ['Thingamajig']"
    )


if __name__ == "__main__":
    main()