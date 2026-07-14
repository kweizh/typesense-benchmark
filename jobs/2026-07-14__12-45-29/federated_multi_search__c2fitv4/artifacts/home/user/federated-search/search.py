"""Federated search across ``products``, ``articles``, and ``users``.

A single Typesense ``multi_search`` request fans the user's query string out
across all three collections. Each sub-query targets its own relevant text
fields (per-query parameters), while shared parameters are sent once as common
parameters. If an individual sub-query fails, only that result slot is marked
as an error and the other collections' results are still returned.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("TYPESENSE_URL", "http://localhost:8108")
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")

# The order here MUST match the order of collections in COLLECTION_KEYS below so
# that each search result slot can be matched up with the collection it came
# from. In federated multi_search the order of results mirrors the order of
# searches in the request.
SUB_QUERIES: list[dict] = [
    {
        # products: search by product_name
        "collection": "products",
        "query_by": "product_name",
    },
    {
        # articles: search by title and body
        "collection": "articles",
        "query_by": "title,body",
    },
    {
        # users: search by username and full_name
        "collection": "users",
        "query_by": "username,full_name",
    },
]

COLLECTION_KEYS: list[str] = [s["collection"] for s in SUB_QUERIES]


def _post_multi_search(body: dict) -> tuple[int, dict]:
    url = f"{BASE_URL}/multi_search"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "X-TYPESENSE-API-KEY": API_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload


def federated_search(query: str) -> dict:
    """Issue a single federated ``multi_search`` request and shape the output.

    The response always contains all three collection keys. A successful
    sub-query becomes ``{"found": <int>, "hits": [<doc>, ...]}``. A failing
    sub-query becomes ``{"error": "<message>"}``.
    """

    # Build the federated multi_search request: each sub-query carries its
    # own ``q`` and ``query_by`` (per-query parameters), while anything we
    # place at the top level would be shared common parameters.
    searches: list[dict] = []
    for spec in SUB_QUERIES:
        searches.append(
            {
                "collection": spec["collection"],
                "q": query,
                "query_by": spec["query_by"],
            }
        )

    payload = {"searches": searches}

    status, body = _post_multi_search(payload)

    if status != 200:
        # Whole-request failure (network, auth, etc.) — represent every
        # collection as an error.
        err_msg = "HTTP request failed"
        if isinstance(body, dict):
            err_msg = str(body.get("error") or body.get("message") or err_msg)
        else:
            err_msg = f"HTTP {status}"
        return {
            "query": query,
            "results": {key: {"error": err_msg} for key in COLLECTION_KEYS},
        }

    raw_results = body.get("results", [])
    results: dict[str, dict] = {}

    # In federated mode, ``results`` is an array whose slots correspond 1:1
    # with the sub-queries we sent. A failing sub-query carries an ``error``
    # (and optionally ``code``) at the slot level; a successful one carries
    # ``hits`` and ``found``.
    for key, slot in zip(COLLECTION_KEYS, raw_results):
        if isinstance(slot, dict) and "error" in slot:
            results[key] = {"error": str(slot.get("error"))}
        else:
            # Unwrap each hit so the array contains the matched document
            # objects themselves (Typesense wraps them with highlight /
            # scoring metadata that we don't want in the public output).
            hits = [
                hit.get("document", hit) if isinstance(hit, dict) else hit
                for hit in slot.get("hits", [])
            ]
            results[key] = {
                "found": int(slot.get("found", 0)),
                "hits": hits,
            }

    # Always include all three keys even if the server returned fewer slots.
    for key in COLLECTION_KEYS:
        results.setdefault(key, {"error": "missing result slot"})

    return {"query": query, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Federated Typesense search")
    parser.add_argument("--query", required=True, help="Query string to search for")
    args = parser.parse_args()

    result = federated_search(args.query)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())