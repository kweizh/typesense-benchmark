#!/usr/bin/env python3
"""
search.py – Search for hubs contained within a polygon.

Usage:
    python3 search.py --polygon "<lat1,lng1,lat2,lng2,...>" [--exclude-status <status>]

Prints a single JSON object to stdout:
    {"hub_ids": ["h01", "h02", ...]}
"""
import argparse
import json
import os
import sys
import typesense

API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HOST = "localhost"
PORT = 8108
COLLECTION_NAME = "hubs"


def get_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [{"host": HOST, "port": PORT, "protocol": "http"}],
            "api_key": API_KEY,
            "connection_timeout_seconds": 10,
        }
    )


def parse_polygon(polygon_str: str) -> str:
    """
    Parse the --polygon argument (comma-separated alternating lat/lng values)
    and return the Typesense polygon filter expression, e.g.:

        location:(37.80,-122.45, 37.80,-122.40, 37.75,-122.40, 37.75,-122.45)

    The input is a flat comma-separated list of alternating latitude and
    longitude values: lat1,lng1,lat2,lng2,...
    """
    parts = [p.strip() for p in polygon_str.split(",") if p.strip() != ""]
    if len(parts) % 2 != 0:
        raise ValueError(
            "Polygon must have an even number of comma-separated "
            "values (alternating lat,lng)."
        )
    if len(parts) < 6:
        raise ValueError("A polygon requires at least 3 vertices (6 values).")

    pairs = []
    for i in range(0, len(parts), 2):
        lat = parts[i]
        lng = parts[i + 1]
        # Validate that they are numeric.
        float(lat)
        float(lng)
        pairs.append(f"{lat},{lng}")

    return "location:(" + ", ".join(pairs) + ")"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search for hubs inside a polygon."
    )
    parser.add_argument(
        "--polygon",
        required=True,
        help="Comma-separated alternating lat/lng values defining the polygon "
        "vertices in order, e.g. '37.80,-122.45,37.80,-122.40,37.75,-122.40,37.75,-122.45'.",
    )
    parser.add_argument(
        "--exclude-status",
        default=None,
        help="Omit hubs whose status equals this value (e.g. 'maintenance').",
    )
    args = parser.parse_args()

    # Build the filter_by expression.
    polygon_filter = parse_polygon(args.polygon)
    filter_by = polygon_filter
    if args.exclude_status:
        filter_by += f" && status:!={args.exclude_status}"

    client = get_client()

    search_params = {
        "q": "*",
        "query_by": "name",
        "filter_by": filter_by,
        "per_page": 250,
    }

    try:
        results = client.collections[COLLECTION_NAME].documents.search(search_params)
    except typesense.exceptions.ObjectNotFound:
        print(json.dumps({"hub_ids": []}))
        return
    except Exception as exc:
        print(f"Search error: {exc}", file=sys.stderr)
        sys.exit(1)

    hits = results.get("hits", [])
    hub_ids = sorted(hit["document"]["id"] for hit in hits)
    print(json.dumps({"hub_ids": hub_ids}))


if __name__ == "__main__":
    main()