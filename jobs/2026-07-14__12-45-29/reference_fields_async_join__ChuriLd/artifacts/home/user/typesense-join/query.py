#!/usr/bin/env python3
"""Query the many-to-many `likes` graph stored in Typesense.

Usage:
    python3 query.py --product <product_id>   -> JSON array of `username` values
    python3 query.py --user    <user_id>      -> JSON array of `product_name` values

The output is sorted in ascending order with duplicates removed (an empty JSON
array is printed when there are no matches). The script talks to the live
Typesense server on http://localhost:8108 and therefore always reflects the
state of the data in the server.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Iterable, List

import typesense
import typesense.exceptions


HOST = "localhost"
PORT = "8108"
PROTOCOL = "http"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")

# Typesense enforces a server-side maximum per-page value (the server defaults to
# 250 via `--max-per-page`). We cap our requests to the known default to stay
# safe on every server configuration while still being large enough for a
# typical social graph; larger result sets are still handled via pagination.
PER_PAGE = 250


def build_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [{"host": HOST, "port": PORT, "protocol": PROTOCOL}],
            "api_key": API_KEY,
            "connection_timeout_seconds": 10,
        }
    )


def _walk_pages(
    client: typesense.Client, search_params: dict[str, Any]
) -> Iterable[dict[str, Any]]:
    """Yield every hit document for a search, transparently paginating."""
    page = 1
    fetched_in_page = 0
    while True:
        params = dict(search_params)
        params["page"] = page
        params["per_page"] = PER_PAGE
        response = client.multi_search.perform({"searches": [params]})
        result = response["results"][0]

        hits = result.get("hits", []) or []
        if not hits:
            return

        for hit in hits:
            doc = hit.get("document", {})
            if doc:
                yield doc

        fetched_in_page = len(hits)
        found = result.get("found", 0)
        if fetched_in_page < PER_PAGE or page * PER_PAGE >= found:
            return
        page += 1


def usernames_for_product(client: typesense.Client, product_id: str) -> List[str]:
    """Return the usernames of every user that liked `product_id`.

    Implementation: search the `users` collection and filter through the
    `likes` linking collection using the asynchronous-reference syntax
    documented by Typesense ($<collection>(<filter>)).
    """
    usernames: list[str] = []
    search_params: dict[str, Any] = {
        "collection": "users",
        "q": "*",
        "filter_by": f"$likes(product_id:={product_id})",
        # `username` is the only field we surface, so we ask for it explicitly
        # and let the CLI rely on Python-side deduplication for correctness.
        "include_fields": "username",
    }
    for doc in _walk_pages(client, search_params):
        username = doc.get("username")
        if isinstance(username, str) and username:
            usernames.append(username)
    # Sort ascending, remove duplicates while preserving order via dict.fromkeys.
    return sorted(set(usernames), key=lambda s: s)


def product_names_for_user(client: typesense.Client, user_id: str) -> List[str]:
    """Return the product_names of every product that `user_id` liked."""
    names: list[str] = []
    search_params: dict[str, Any] = {
        "collection": "products",
        "q": "*",
        "filter_by": f"$likes(user_id:={user_id})",
        "include_fields": "product_name",
    }
    for doc in _walk_pages(client, search_params):
        product_name = doc.get("product_name")
        if isinstance(product_name, str) and product_name:
            names.append(product_name)
    return sorted(set(names), key=lambda s: s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Many-to-many join queries over the Typesense likes graph."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--product", help="Product id; list usernames who liked it.")
    group.add_argument("--user", help="User id; list product names they liked.")
    args = parser.parse_args(argv)

    try:
        client = build_client()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[error] could not initialise Typesense client: {exc}", file=sys.stderr)
        return 2

    if args.product is not None:
        try:
            result = usernames_for_product(client, args.product)
        except typesense.exceptions.TypesenseClientError as exc:
            print(f"[error] query failed: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            result = product_names_for_user(client, args.user)
        except typesense.exceptions.TypesenseClientError as exc:
            print(f"[error] query failed: {exc}", file=sys.stderr)
            return 1

    # Always print a valid JSON array on stdout, even when empty.
    sys.stdout.write(json.dumps(result))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
