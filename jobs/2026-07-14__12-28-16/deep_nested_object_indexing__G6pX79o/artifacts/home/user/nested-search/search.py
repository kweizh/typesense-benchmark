#!/usr/bin/env python3
"""
Query tool for the nested_orders Typesense collection.

Usage:
    python3 /home/user/nested-search/search.py --keyword <text> --color <color>

Searches the deeply nested product-name path (orders.line_items.name) with the
given keyword, keeps only documents that contain a line item whose nested
attributes.color exactly equals <color>, and reports faceted category counts
over the nested category path (orders.line_items.category).

Prints exactly one JSON object to stdout with two keys:
    - matched_customer_ids: list of matching document ids, sorted ascending.
    - category_facet_counts: {category: count of matched documents containing it}
"""

import argparse
import json
import sys

import requests

TYPESENSE_HOST = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION_NAME = "nested_orders"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

# Nested field paths relied upon.
NAME_FIELD = "orders.line_items.name"
COLOR_FIELD = "orders.line_items.attributes.color"
CATEGORY_FIELD = "orders.line_items.category"


def search(keyword, color):
    # Build the search request.
    params = {
        "collection": COLLECTION_NAME,
        "q": keyword,
        "query_by": NAME_FIELD,
        "filter_by": f"{COLOR_FIELD}:=[`{color}`]",
        "facet_by": CATEGORY_FIELD,
        "per_page": 250,
    }

    r = requests.get(
        f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}/documents/search",
        headers=HEADERS,
        params=params,
    )
    r.raise_for_status()
    results = r.json()

    # Extract matching document ids.
    matched_ids = sorted(hit["document"]["id"] for hit in results.get("hits", []))

    # Build category facet counts from Typesense facet_counts. Typesense counts
    # each document once per distinct facet value it contains, which matches the
    # requirement (a document is counted once per distinct category it contains).
    category_facet_counts = {}
    for facet in results.get("facet_counts", []):
        if facet["field_name"] == CATEGORY_FIELD:
            for c in facet["counts"]:
                category_facet_counts[c["value"]] = c["count"]

    return {
        "matched_customer_ids": matched_ids,
        "category_facet_counts": category_facet_counts,
    }


def main():
    parser = argparse.ArgumentParser(description="Search nested_orders collection")
    parser.add_argument("--keyword", required=True, help="Keyword to search product names")
    parser.add_argument("--color", required=True, help="Exact color to filter by")
    args = parser.parse_args()

    result = search(args.keyword, args.color)
    print(json.dumps(result))


if __name__ == "__main__":
    main()