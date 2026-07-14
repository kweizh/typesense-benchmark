#!/usr/bin/env python3
"""Federated search across the `products`, `articles`, and `users` collections.

Given a single query string, this command fans it out across all three
collections in *one* federated Typesense `multi_search` request and prints one
grouped result set per collection as a single JSON object on stdout.

Design notes
------------
* A single HTTP POST to `/multi_search` carries all three sub-queries. This is
  the federated model: each sub-query targets its own collection and returns an
  independent result set, in the same order as the sub-queries were sent.
* Shared parameters (`q`, `per_page`) are passed once as common URL query
  parameters so they apply to every sub-query. Per-query parameters
  (`collection`, `query_by`) live inside each individual search object in the
  `searches` array, because each collection has a different schema and must be
  searched against its own text fields.
* Resilience: in a federated `multi_search`, an individual failing sub-query
  does not fail the whole HTTP request — its result slot carries an error
  object (a `code`/`error` pair) instead of hits. We inspect every slot and, if
  a slot failed, surface an `error` entry for that collection while still
  returning the successful collections' results. All three collection keys are
  always present in the output.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TYPESENSE_HOST = os.environ.get("TYPESENSE_HOST", "http://localhost:8108")
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")

# The collections to search, in the order they are sent to multi_search. The
# order matters: the i-th element of the `results` array in the response
# corresponds to the i-th element here.
COLLECTIONS = ["products", "articles", "users"]

# Per-collection searchable text fields. These are the per-query `query_by`
# parameters that differ between collections because each has its own schema.
QUERY_BY = {
    "products": "product_name",
    "articles": "title,body",
    "users": "username,full_name",
}

# Page size applied to every sub-query via the common `per_page` parameter.
PER_PAGE = 50


def multi_search(query):
    """Run a single federated multi_search and return the parsed `results` list.

    Returns a list with one entry per collection, in COLLECTIONS order. A
    successful entry is the raw Typesense search-result object (containing
    `found` and `hits`); a failed entry is an error object with `code`/`error`.
    If the whole HTTP request fails, every entry is an error object.
    """
    # Per-query objects: only the parameters that vary per collection go here.
    searches = [
        {"collection": name, "query_by": QUERY_BY[name]}
        for name in COLLECTIONS
    ]
    body = json.dumps({"searches": searches}).encode("utf-8")

    # Shared parameters are passed once as common URL query parameters so they
    # apply to every sub-query in the batch.
    common_params = urllib.parse.urlencode({"q": query, "per_page": PER_PAGE})
    url = f"{TYPESENSE_HOST}/multi_search?{common_params}"

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The entire multi_search request failed. We cannot attribute the
        # failure to a single collection, so mark every collection as errored.
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = detail.get("message") or detail.get("error") or str(detail)
        except (ValueError, OSError):
            message = f"HTTP {exc.code}: {exc.reason}"
        return [{"code": exc.code, "error": message} for _ in COLLECTIONS]
    except urllib.error.URLError as exc:
        # Server unreachable / network problem: mark every collection errored.
        message = f"Could not reach Typesense at {TYPESENSE_HOST}: {exc.reason}"
        return [{"code": 0, "error": message} for _ in COLLECTIONS]

    results = payload.get("results", [])
    # Defensive padding: ensure we have exactly one slot per collection even if
    # the server returned fewer (or more) result slots than expected.
    while len(results) < len(COLLECTIONS):
        results.append({"code": 0, "error": "Missing result slot from multi_search."})
    return results[:len(COLLECTIONS)]


def build_output(query, slots):
    """Translate the raw multi_search result slots into the output shape."""
    output = {"query": query, "results": {}}
    for name, slot in zip(COLLECTIONS, slots):
        # A failed sub-query slot carries a `code`/`error` pair (no `hits`).
        if isinstance(slot, dict) and ("error" in slot or "code" in slot) and "hits" not in slot:
            message = slot.get("error") or f"sub-query failed (code {slot.get('code')})"
            output["results"][name] = {"error": message}
        else:
            found = slot.get("found", 0)
            # Each hit wraps the matched document under a `document` key; the
            # output exposes the bare document object (which includes `id`).
            hits = [hit.get("document", hit) for hit in slot.get("hits", [])]
            output["results"][name] = {"found": found, "hits": hits}
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Federated search across products, articles, and users via "
                    "a single Typesense multi_search request."
    )
    parser.add_argument(
        "--query", required=True,
        help="The query string to fan out across all three collections."
    )
    args = parser.parse_args(argv)

    slots = multi_search(args.query)
    output = build_output(args.query, slots)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())