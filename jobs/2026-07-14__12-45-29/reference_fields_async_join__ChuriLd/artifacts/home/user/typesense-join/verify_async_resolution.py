#!/usr/bin/env python3
"""Verify the asynchronous reference resolution behaviour explicitly.

We pick brand-new ids that don't yet exist and:
  1. Insert a `likes` document pointing at the not-yet-existing user + product
  2. Confirm the like is indexed (search returns it) even though the
     referenced documents are missing
  3. Index the missing user and product
  4. Confirm that the previously-broken references now resolve (the joined
     fields appear in the search result)
"""

import json
import sys
import time

import typesense

client = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": "xyz",
        "connection_timeout_seconds": 10,
    }
)

LIKES = client.collections["likes"].documents
USERS = client.collections["users"].documents
PRODUCTS = client.collections["products"].documents


def fetch_my_doc(target_id):
    """Return the joined document for `target_id` after $likes(search by id)."""
    return client.multi_search.perform(
        {
            "searches": [
                {
                    "collection": "likes",
                    "q": "*",
                    "filter_by": f"id:={target_id}",
                    "include_fields": "$users(username),$products(product_name)",
                }
            ]
        }
    )["results"][0]["hits"][0]["document"]


async_user = "u-async-verify"
async_product = "p-async-verify"
async_like = "like-async-verify"

try:
    # ---------------------------------------------------------------------------
    # 1. Index a like pointing at non-existent targets
    # ---------------------------------------------------------------------------
    res = LIKES.create(
        {"id": async_like, "user_id": async_user, "product_id": async_product}
    )
    print(f"[step 1] created like pointing at missing user/product: {res}")
    doc = fetch_my_doc(async_like)
    print(f"[step 1] document just after index: {json.dumps(doc)}")
    # We expect the nested `users` / `products` join objects to be ABSENT here
    # because the referenced documents don't exist yet.
    assert "users" not in doc, "unexpected: user reference already resolved?"
    assert "products" not in doc, "unexpected: product reference already resolved?"
    print("[step 1] async index accepted (joined fields still unresolved)")

    # ---------------------------------------------------------------------------
    # 2. Now index the missing user and product
    # ---------------------------------------------------------------------------
    USERS.create({"id": async_user, "username": "async_user"})
    PRODUCTS.create({"id": async_product, "product_name": "AsyncProduct"})
    print(f"[step 2] indexed the previously-missing {async_user} and {async_product}")

    # ---------------------------------------------------------------------------
    # 3. Wait a bit and verify the references resolved automatically.
    # ---------------------------------------------------------------------------
    deadline = time.time() + 10
    resolved = False
    while time.time() < deadline:
        doc = fetch_my_doc(async_like)
        if (
            isinstance(doc.get("users"), dict)
            and doc["users"].get("username") == "async_user"
            and isinstance(doc.get("products"), dict)
            and doc["products"].get("product_name") == "AsyncProduct"
        ):
            resolved = True
            break
        time.sleep(0.5)

    print(f"[step 3] document after waiting: {json.dumps(doc)}")
    assert resolved, "references did NOT resolve asynchronously within timeout"
    print("[step 3] asynchronous reference resolution CONFIRMED")

    # ---------------------------------------------------------------------------
    # 4. Verify the CLI can answer this through the join.
    # ---------------------------------------------------------------------------
finally:
    for target, target_id in [
        (LIKES, async_like),
        (USERS, async_user),
        (PRODUCTS, async_product),
    ]:
        try:
            target[target_id].delete()
        except typesense.exceptions.ObjectNotFound:
            pass

print("\nAsync reference resolution verification PASSED.")
