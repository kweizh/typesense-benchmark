#!/usr/bin/env python3
"""
search.py — Federated search across products, articles, and users via
Typesense multi_search.

Usage:
    python3 search.py --query "<query string>"

Output:
    A single JSON object written to stdout:

    {
      "query": "<query string>",
      "results": {
        "products": { "found": <int>, "hits": [ { ...document... }, ... ] },
        "articles": { "found": <int>, "hits": [ { ...document... }, ... ] },
        "users":    { "found": <int>, "hits": [ { ...document... }, ... ] }
                 -- OR --
        "users":    { "error": "<message>" }
      }
    }

Environment:
    TYPESENSE_API_KEY   API key (default: xyz)
    TYPESENSE_HOST      Host (default: localhost)
    TYPESENSE_PORT      Port (default: 8108)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HOST = os.environ.get("TYPESENSE_HOST", "localhost")
PORT = int(os.environ.get("TYPESENSE_PORT", "8108"))
BASE_URL = f"http://{HOST}:{PORT}"

# ---------------------------------------------------------------------------
# Per-collection search fields
# Collections are listed in the order we want them in the output.
# ---------------------------------------------------------------------------
COLLECTION_FIELDS = {
    "products": "product_name",
    "articles": "title,body",
    "users":    "username,full_name",
}

# ---------------------------------------------------------------------------
# Core search logic
# ---------------------------------------------------------------------------

def multi_search(query: str) -> dict:
    """
    Send a single federated multi_search request to Typesense.

    Common parameters (q, per_page) are hoisted to the query string.
    Per-collection parameters (collection, query_by) are kept in each
    individual search object inside the POST body.

    Returns a dict shaped as the 'results' portion of the final output.
    """

    # -- Build the request body ------------------------------------------------
    searches = [
        {"collection": collection, "query_by": fields}
        for collection, fields in COLLECTION_FIELDS.items()
    ]
    body = json.dumps({"searches": searches}).encode()

    # -- Common parameters on the query string ---------------------------------
    # q and per_page apply to every sub-query.
    common_params = urllib.parse.urlencode({"q": query, "per_page": 10})
    url = f"{BASE_URL}/multi_search?{common_params}"

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-TYPESENSE-API-KEY": API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    # -- Execute the request ---------------------------------------------------
    try:
        with urllib.request.urlopen(req) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # The whole HTTP request failed (network issue, auth error, etc.).
        # Represent every collection as an error.
        error_msg = f"HTTP {exc.code}: {exc.read().decode(errors='replace')}"
        return {col: {"error": error_msg} for col in COLLECTION_FIELDS}
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        return {col: {"error": error_msg} for col in COLLECTION_FIELDS}

    # -- Parse per-collection result slots -------------------------------------
    result_slots: list[dict] = raw.get("results", [])
    output: dict = {}

    for (collection, _fields), slot in zip(COLLECTION_FIELDS.items(), result_slots):
        # A failing sub-query carries a "code"/"error" pair instead of "hits".
        if "error" in slot or "code" in slot:
            error_text = slot.get("error") or f"code {slot.get('code')}"
            output[collection] = {"error": error_text}
        else:
            output[collection] = {
                "found": slot.get("found", 0),
                "hits": [
                    hit["document"]
                    for hit in slot.get("hits", [])
                ],
            }

    # Guard: if the server returned fewer slots than we sent searches
    # (shouldn't happen, but be defensive).
    for collection in COLLECTION_FIELDS:
        if collection not in output:
            output[collection] = {"error": "no result slot returned by server"}

    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Federated search across products, articles, and users."
    )
    parser.add_argument(
        "--query", "-q",
        required=True,
        help="The search query string.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    query: str = args.query

    results = multi_search(query)

    output = {
        "query": query,
        "results": results,
    }

    print(json.dumps(output, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
