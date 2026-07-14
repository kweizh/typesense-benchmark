#!/usr/bin/env python3
"""
Search for delivery hubs contained within a caller-supplied polygon.

Usage:
    python3 search.py --polygon "lat1,lng1,lat2,lng2,..." [--exclude-status <status>]

Output (stdout):
    {"hub_ids": ["h01", "h02"]}   -- sorted ascending lexicographically
    {"hub_ids": []}               -- when nothing matches
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

HOST = "http://localhost:8108"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "")
if not API_KEY:
    print("ERROR: TYPESENSE_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

COLLECTION_NAME = "hubs"


def build_polygon_filter(polygon_str: str) -> str:
    """
    Convert a flat comma-separated "lat1,lng1,lat2,lng2,..." string into
    Typesense's polygon filter syntax: location:(lat1,lng1,lat2,lng2,...)
    """
    values = [v.strip() for v in polygon_str.split(",")]
    if len(values) < 6 or len(values) % 2 != 0:
        print(
            "ERROR: --polygon requires at least 3 coordinate pairs (6 values) "
            "and must have an even number of values.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Validate all values are numeric
    try:
        [float(v) for v in values]
    except ValueError as exc:
        print(f"ERROR: Non-numeric value in --polygon: {exc}", file=sys.stderr)
        sys.exit(1)
    return f"location:({','.join(values)})"


def search_hubs(polygon_str: str, exclude_status: str | None) -> list[str]:
    polygon_filter = build_polygon_filter(polygon_str)

    filter_parts = [polygon_filter]
    if exclude_status:
        # Typesense not-equal operator: field:!=value
        filter_parts.append(f"status:!={exclude_status}")

    filter_by = " && ".join(filter_parts)

    params = {
        "q": "*",
        "query_by": "name",
        "filter_by": filter_by,
        "per_page": "250",  # well above any realistic hub count
        "page": "1",
    }

    url = f"{HOST}/collections/{COLLECTION_NAME}/documents/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Search request failed (HTTP {e.code}): {body}", file=sys.stderr)
        sys.exit(1)

    hits = data.get("hits", [])
    hub_ids = sorted(hit["document"]["id"] for hit in hits)
    return hub_ids


def main():
    parser = argparse.ArgumentParser(
        description="Search for hubs inside a polygon, optionally excluding by status."
    )
    parser.add_argument(
        "--polygon",
        required=True,
        help=(
            'Comma-separated alternating lat/lng values defining the polygon vertices, '
            'e.g. "37.80,-122.45,37.80,-122.40,37.76,-122.40,37.76,-122.45"'
        ),
    )
    parser.add_argument(
        "--exclude-status",
        default=None,
        help="Exclude hubs whose status equals this value (e.g. maintenance).",
    )
    args = parser.parse_args()

    hub_ids = search_hubs(args.polygon, args.exclude_status)
    print(json.dumps({"hub_ids": hub_ids}))


if __name__ == "__main__":
    main()
