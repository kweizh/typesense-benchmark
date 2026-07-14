#!/usr/bin/env python3
"""
search.py - Query tool for nested_orders Typesense collection.

Usage:
    python3 search.py --keyword <text> --color <color>

Output (stdout):
    A single JSON object with:
      - matched_customer_ids: sorted list of matching document IDs
      - category_facet_counts: dict mapping category -> count of matched docs
        containing that category (each doc counted once per distinct category)
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
import urllib.error

TYPESENSE_HOST = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION = "nested_orders"


def search(keyword: str, color: str) -> dict:
    """
    Search nested_orders for documents whose line item names match `keyword`
    and that contain at least one line item with attributes.color == `color`.
    Returns facet counts for the `orders.line_items.category` field.
    """
    params = urllib.parse.urlencode({
        "q": keyword,
        "query_by": "orders.line_items.name",
        "filter_by": f"orders.line_items.attributes.color:={color}",
        "facet_by": "orders.line_items.category",
        "per_page": 250,
        "page": 1,
    })

    url = f"{TYPESENSE_HOST}/collections/{COLLECTION}/documents/search?{params}"
    req = urllib.request.Request(url, headers={"X-TYPESENSE-API-KEY": API_KEY})

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"HTTP error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    # --- Extract matched customer IDs ---
    matched_ids = sorted(hit["document"]["id"] for hit in data.get("hits", []))

    # --- Build category facet counts from Typesense facet_counts ---
    # Typesense facet_counts aggregate at the document level: each document is
    # counted once per distinct category value it contains among matched docs.
    # This matches the requirement exactly.
    category_facet_counts = {}
    for facet in data.get("facet_counts", []):
        if facet["field_name"] == "orders.line_items.category":
            for entry in facet["counts"]:
                category_facet_counts[entry["value"]] = entry["count"]
            break

    return {
        "matched_customer_ids": matched_ids,
        "category_facet_counts": category_facet_counts,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Search nested_orders collection by keyword and color filter."
    )
    parser.add_argument("--keyword", required=True, help="Keyword to search in product names")
    parser.add_argument("--color", required=True, help="Color to filter by (exact match)")
    args = parser.parse_args()

    result = search(args.keyword, args.color)
    # Print exactly one JSON object to stdout, nothing else
    print(json.dumps(result))


if __name__ == "__main__":
    main()
