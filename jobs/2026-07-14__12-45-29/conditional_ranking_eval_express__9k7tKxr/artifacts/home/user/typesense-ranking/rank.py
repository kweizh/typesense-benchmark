#!/usr/bin/env python3
"""Query script: search the `catalog` collection with promotion-aware ranking.

Run with:  python3 rank.py --query "Alpine"

The output is a single line of JSON - the ordered list of document `id`s, e.g.:

    ["P5","P3","P2","P1","P6","P4"]

Nothing else is printed on stdout so the result can be piped safely.

Ranking policy:
    1. Promotion tier (dominant): `sponsored` > `featured` > everything else.
       This tier is *computed* per-query with the conditional score operator
       inside Typesense's `_eval()` / sort_by grammar.
    2. Text relevance within a tier: a document that matches the query across
       BOTH `title` AND `description` is more relevant than one that matches
       in only one field. We achieve this by setting `text_match_type=sum_score`
       which sums per-field text match scores - the default `max_score` would
       NOT reward extra field matches.
    3. Final tie-breaker: higher `popularity` wins.

Note that `sort_by` accepts at most 3 fields - we use all three for tier,
relevance, and popularity.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import typesense

# --- Configuration (matches setup.py) -------------------------------------
TYPESENSE_HOST = os.environ.get("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT = os.environ.get("TYPESENSE_PORT", "8108")
TYPESENSE_PROTOCOL = os.environ.get("TYPESENSE_PROTOCOL", "http")
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
COLLECTION_NAME = "catalog"

# Three-field sort_by grammar in priority order:
#  * _eval(): conditional score (sponsored=3 > featured=2 > rest=1)
#  * _text_match:desc: text relevance with multi-field reward (sum_score)
#  * popularity:desc: numeric tie-breaker for exact ties
SORT_BY = (
    "_eval("
    "[(badge:sponsored):3, (badge:featured):2, (badge:none):1]"
    "):desc,"
    "_text_match:desc,"
    "popularity:desc"
)


def make_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [
                {"host": TYPESENSE_HOST, "port": TYPESENSE_PORT, "protocol": TYPESENSE_PROTOCOL}
            ],
            "api_key": TYPESENSE_API_KEY,
            "connection_timeout_seconds": 5,
        }
    )


def search(client: typesense.Client, query: str) -> list[str]:
    """Run the search and return an ordered list of matching document ids."""
    result = client.collections[COLLECTION_NAME].documents.search(
        {
            "q": query,
            "query_by": "title,description",
            # Multi-field text-match scoring mode:
            # `sum_score` adds up the per-field text match scores so a doc that
            # matches the query in both `title` AND `description` scores higher
            # than a doc that matches in just one of those fields. The default
            # `max_score` mode would not reward the additional field.
            "text_match_type": "sum_score",
            "sort_by": SORT_BY,
            # Be explicit: return only what we need, page through everything
            "page": 1,
            "per_page": 100,
        }
    )
    return [hit["document"]["id"] for hit in result.get("hits", [])]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Typesense search against the `catalog` collection "
        "and print the ranked document ids as JSON.",
    )
    parser.add_argument(
        "--query",
        required=True,
        help="The shopper's search query (matched against title + description).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = make_client()
    ids = search(client, args.query)
    # ONLY the JSON array on stdout - no logs, no banners.
    json.dump(ids, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
