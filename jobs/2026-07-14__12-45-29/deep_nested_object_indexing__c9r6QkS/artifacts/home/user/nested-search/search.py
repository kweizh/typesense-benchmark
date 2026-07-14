#!/usr/bin/env python3
"""Search the nested_orders Typesense collection.

Usage:
    python3 /home/user/nested-search/search.py --keyword <text> --color <color>

Searches the nested product-name path (`orders.line_items.name`) for the given
keyword, restricts the result to documents that have at least one line item with
`orders.line_items.attributes.color` equal to <color>, and reports faceted
counts over the nested `orders.line_items.category` path.

Prints exactly one JSON object to stdout with:
  - matched_customer_ids: sorted list of matching document ids
  - category_facet_counts: {category: document_count} for the matched documents
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

TYPESENSE_HOST = "http://localhost:8108"
TYPESENSE_API_KEY = "xyz"
COLLECTION_NAME = "nested_orders"
NAME_FIELD = "orders.line_items.name"
COLOR_FIELD = "orders.line_items.attributes.color"
CATEGORY_FIELD = "orders.line_items.category"

PER_PAGE = 250  # pagination chunk size


def search_all_pages(keyword: str, color: str) -> dict:
    """Run a Typesense search and paginate through all matching documents.

    Returns the merged search response, with `hits` containing every matched
    document and `facet_counts` reflecting the full result set.
    """
    page = 1
    merged_hits = []
    facet_counts = []
    found = 0
    out_of = 0

    while True:
        params = {
            "q": keyword,
            "query_by": NAME_FIELD,
            "filter_by": f"{COLOR_FIELD}:={color}",
            "facet_by": CATEGORY_FIELD,
            "per_page": PER_PAGE,
            "page": page,
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}/documents/search?{query_string}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"X-TYPESENSE-API-KEY": TYPESENSE_API_KEY},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Typesense search failed (HTTP {exc.code}): {detail}"
            ) from exc

        merged_hits.extend(body.get("hits", []))
        found = body.get("found", len(merged_hits))
        out_of = body.get("out_of", found)

        if page == 1:
            facet_counts = body.get("facet_counts", [])

        if len(merged_hits) >= found or not body.get("hits"):
            break
        page += 1

    return {
        "hits": merged_hits,
        "found": found,
        "out_of": out_of,
        "facet_counts": facet_counts,
    }


def collect_category_facet(facet_counts: list) -> dict:
    """Extract {category: count} from Typesense facet_counts for the category field."""
    counts = {}
    for facet in facet_counts or []:
        if facet.get("field_name") != CATEGORY_FIELD:
            continue
        for bucket in facet.get("counts", []):
            value = bucket.get("value")
            count = bucket.get("count", 0)
            if value is not None:
                counts[value] = count
    return counts


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search the nested_orders Typesense collection by keyword and color "
            "and report per-category facet counts."
        )
    )
    parser.add_argument("--keyword", required=True, help="Search keyword")
    parser.add_argument("--color", required=True, help="Exact color to filter on")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    response = search_all_pages(args.keyword, args.color)

    matched_ids = sorted(
        hit["document"]["id"] for hit in response.get("hits", []) if "id" in hit.get("document", {})
    )
    category_facet_counts = collect_category_facet(response.get("facet_counts", []))

    output = {
        "matched_customer_ids": matched_ids,
        "category_facet_counts": category_facet_counts,
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())