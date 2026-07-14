#!/usr/bin/env python3
"""
query.py — Many-to-many join queries over the users/products/likes collections.

Usage:
    python3 query.py --product <product_id>
        Print a JSON array of usernames of every user who liked that product,
        sorted ascending, deduped.

    python3 query.py --user <user_id>
        Print a JSON array of product_names of every product that user liked,
        sorted ascending, deduped.

Examples:
    python3 query.py --product p1
    python3 query.py --user u1
"""

import argparse
import json
import os
import sys

import requests

API_KEY  = os.environ.get("TYPESENSE_API_KEY", "xyz")
BASE_URL = "http://localhost:8108"
HEADERS  = {"X-TYPESENSE-API-KEY": API_KEY}


def search(collection: str, params: dict) -> dict:
    """Run a search against *collection* and return the parsed JSON response."""
    r = requests.get(
        f"{BASE_URL}/collections/{collection}/documents/search",
        headers=HEADERS,
        params=params,
    )
    if not r.ok:
        sys.exit(f"ERROR: Typesense search failed: {r.status_code} {r.text}")
    return r.json()


def get_users_for_product(product_id: str) -> list[str]:
    """
    Return sorted, deduped list of usernames of users who liked *product_id*.

    Strategy: search the `likes` linking collection filtered by product_id,
    then join in the `users` collection to fetch the username field.

      filter_by  : product_id:=<product_id>
                   AND $users(id:*)           ← join condition (all users)
      include_fields: $users(username)        ← pull username from joined doc
    """
    params = {
        "q":              "*",
        "query_by":       "product_id",
        "filter_by":      f"product_id:={product_id} && $users(id:*)",
        "include_fields": "$users(username)",
        "per_page":       250,
        "page":           1,
    }

    usernames: set[str] = set()
    while True:
        data = search("likes", params)
        hits = data.get("hits", [])
        if not hits:
            break
        for hit in hits:
            doc = hit.get("document", {})
            # Joined fields are nested under the collection name
            user_info = doc.get("users", {})
            if isinstance(user_info, dict):
                uname = user_info.get("username")
                if uname:
                    usernames.add(uname)
        # Paginate if needed
        found = data.get("found", 0)
        page  = params["page"]
        if page * params["per_page"] >= found:
            break
        params["page"] += 1

    return sorted(usernames)


def get_products_for_user(user_id: str) -> list[str]:
    """
    Return sorted, deduped list of product_names of products liked by *user_id*.

    Strategy: search the `likes` linking collection filtered by user_id,
    then join in the `products` collection to fetch the product_name field.

      filter_by  : user_id:=<user_id>
                   AND $products(id:*)        ← join condition (all products)
      include_fields: $products(product_name) ← pull product_name from joined doc
    """
    params = {
        "q":              "*",
        "query_by":       "user_id",
        "filter_by":      f"user_id:={user_id} && $products(id:*)",
        "include_fields": "$products(product_name)",
        "per_page":       250,
        "page":           1,
    }

    product_names: set[str] = set()
    while True:
        data = search("likes", params)
        hits = data.get("hits", [])
        if not hits:
            break
        for hit in hits:
            doc = hit.get("document", {})
            product_info = doc.get("products", {})
            if isinstance(product_info, dict):
                pname = product_info.get("product_name")
                if pname:
                    product_names.add(pname)
        found = data.get("found", 0)
        page  = params["page"]
        if page * params["per_page"] >= found:
            break
        params["page"] += 1

    return sorted(product_names)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query many-to-many likes joins in Typesense.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--product",
        metavar="PRODUCT_ID",
        help="Print usernames of all users who liked this product.",
    )
    group.add_argument(
        "--user",
        metavar="USER_ID",
        help="Print product_names of all products this user liked.",
    )
    args = parser.parse_args()

    if args.product:
        result = get_users_for_product(args.product)
    else:
        result = get_products_for_user(args.user)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
