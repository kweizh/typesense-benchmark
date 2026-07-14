#!/usr/bin/env python3
"""Polygon point-in-polygon search for the `hubs` collection.

Example:
    python3 search.py \\
        --polygon "37.78,-122.46,37.82,-122.46,37.82,-122.38,37.78,-122.38" \\
        --exclude-status maintenance

Prints a single JSON object, e.g. {"hub_ids": ["h01", "h02", ...]}, with the
ids sorted in ascending lexicographic order.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import typesense


API_KEY = os.environ.get("TYPESENSE_API_KEY")
if not API_KEY:
    print("ERROR: TYPESENSE_API_KEY environment variable must be set", file=sys.stderr)
    sys.exit(1)

COLLECTION_NAME = "hubs"


def parse_polygon(polygon_arg: str) -> list[tuple[float, float]]:
    """Parse a comma-separated polygon string into [(lat, lng), ...].

    The argument is a single string with alternating latitude and longitude
    values separated by commas. Whitespace inside the string is allowed but
    ignored.
    """
    tokens = [tok for tok in re.split(r"\s*,\s*", polygon_arg.strip()) if tok != ""]
    if len(tokens) < 6 or len(tokens) % 2 != 0:
        raise argparse.ArgumentTypeError(
            "--polygon needs at least 3 vertices (6 numbers), each pair is (lat, lng)"
        )
    vertices: list[tuple[float, float]] = []
    for i in range(0, len(tokens), 2):
        try:
            lat = float(tokens[i])
            lng = float(tokens[i + 1])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"--polygon: could not parse {tokens[i]!r}/{tokens[i + 1]!r} as numbers: {exc}"
            ) from exc
        vertices.append((lat, lng))
    return vertices


def polygon_filter(vertices: list[tuple[float, float]]) -> str:
    """Build a Typesense `filter_by` clause for a polygon containment test.

    Typesense geopoint values are stored as [latitude, longitude], so the
    vertices must be emitted in that same order.
    """
    parts: list[str] = []
    for lat, lng in vertices:
        parts.append(f"{lat},{lng}")
    return f"location:({','.join(parts)})"


def run_search(client: typesense.Client, filter_by: str) -> list[str]:
    """Run the search and return the matching hub ids.

    Paginated so we never silently drop documents because of small
    per_page defaults.
    """
    ids: list[str] = []
    page = 1
    per_page = 100
    while True:
        results = client.collections[COLLECTION_NAME].documents.search(
            {
                "q": "*",
                "filter_by": filter_by,
                "page": page,
                "per_page": per_page,
            }
        )
        hits = results.get("hits", [])
        if not hits:
            break
        for hit in hits:
            doc = hit.get("document", {})
            doc_id = doc.get("id")
            if doc_id is not None:
                ids.append(doc_id)
        if len(hits) < per_page:
            break
        page += 1
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Return hub ids contained within the given polygon."
    )
    parser.add_argument(
        "--polygon",
        required=True,
        type=parse_polygon,
        help=(
            "Polygon vertices as a single comma-separated string of alternating "
            "latitude,longitude numbers, e.g. "
            '"37.78,-122.46,37.82,-122.46,37.82,-122.38,37.78,-122.38".'
        ),
    )
    parser.add_argument(
        "--exclude-status",
        default=None,
        help="If provided, omit hubs whose status equals this value.",
    )
    args = parser.parse_args()

    client = typesense.Client(
        {
            "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
            "api_key": API_KEY,
            "connection_timeout_seconds": 5,
        }
    )

    clauses = [polygon_filter(args.polygon)]
    if args.exclude_status is not None:
        # Status filter: equality on `status`, but use `!=` for exclusion.
        # The value is wrapped in backticks so any non-identifier characters
        # in `args.exclude_status` are still parsed literally.
        clauses.append(f"status:!={args.exclude_status}")
    filter_by = " && ".join(clauses)

    ids = run_search(client, filter_by)
    ids.sort()  # ascending lexicographic, as required by the spec.

    print(json.dumps({"hub_ids": ids}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
