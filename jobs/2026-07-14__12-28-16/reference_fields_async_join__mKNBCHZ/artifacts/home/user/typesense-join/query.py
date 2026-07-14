#!/usr/bin/env python3
"""
Rerunnable query CLI for the Typesense many-to-many "likes" graph.

Answers many-to-many join queries by filtering through the linking `likes`
collection and joining to the referenced collection:

  python3 query.py --product <product_id>
      -> JSON array of `username` values of every user who liked that product,
         sorted ascending, duplicates removed.

  python3 query.py --user <user_id>
      -> JSON array of `product_name` values of every product that user liked,
         sorted ascending, duplicates removed.

If there are no matches, an empty JSON array `[]` is printed.

The CLI always queries the live Typesense server on port 8108, so it reflects
any data added to the server after the initial seeding step.
"""

import argparse
import json
import os
import sys

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


def _extract_joined_field(doc, joined_collection, field):
    """
    Pull a field value out of a nested joined-collection object returned by
    Typesense.  With the default `nest` strategy the joined collection's
    fields appear under a key named after the collection, e.g. document
    {"users": {"username": "alice"}, ...}.
    """
    joined = doc.get(joined_collection)
    if isinstance(joined, dict):
        val = joined.get(field)
        if val is not None:
            return [val]
        # Some responses nest the fields under a list of objects.
    if isinstance(joined, list):
        vals = []
        for item in joined:
            if isinstance(item, dict) and item.get(field) is not None:
                vals.append(item[field])
        return vals
    return []


def query_users_for_product(client, product_id):
    """
    Return the sorted, de-duplicated list of usernames of every user who
    liked `product_id`.

    Strategy: search the linking `likes` collection, filter by the product
    reference field, and join the `users` collection to fetch the username.
    """
    results = []
    page = 1
    per_page = 250
    while True:
        res = client.collections["likes"].documents.search(
            {
                "q": "*",
                "query_by": "",
                "filter_by": f"product_id:={product_id}",
                "include_fields": "$users(username)",
                "per_page": per_page,
                "page": page,
            }
        )
        hits = res.get("hits", [])
        for hit in hits:
            results.extend(_extract_joined_field(hit["document"], "users", "username"))
        if len(hits) < per_page:
            break
        page += 1

    return sorted(set(results))


def query_products_for_user(client, user_id):
    """
    Return the sorted, de-duplicated list of product_names of every product
    that `user_id` liked.

    Strategy: search the linking `likes` collection, filter by the user
    reference field, and join the `products` collection to fetch the
    product_name.
    """
    results = []
    page = 1
    per_page = 250
    while True:
        res = client.collections["likes"].documents.search(
            {
                "q": "*",
                "query_by": "",
                "filter_by": f"user_id:={user_id}",
                "include_fields": "$products(product_name)",
                "per_page": per_page,
                "page": page,
            }
        )
        hits = res.get("hits", [])
        for hit in hits:
            results.extend(
                _extract_joined_field(hit["document"], "products", "product_name")
            )
        if len(hits) < per_page:
            break
        page += 1

    return sorted(set(results))


def main():
    parser = argparse.ArgumentParser(
        description="Query the Typesense many-to-many likes graph."
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

    client = get_client()

    try:
        if args.product is not None:
            output = query_users_for_product(client, args.product)
        else:
            output = query_products_for_user(client, args.user)
    except typesense.exceptions.TypesenseClientError as exc:
        print(f"Query error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(output))


if __name__ == "__main__":
    main()