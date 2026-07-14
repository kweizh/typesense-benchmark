#!/usr/bin/env python3
"""
Search the `airports` Typesense collection for airports within a radius of a
given coordinate, sorted by ascending great-circle distance.

Usage:
    python3 /home/user/project/search.py \
        --lat 49.0097 --lng 2.5479 --radius-km 100

The script prints a single JSON object to stdout with keys:
    reference:  {"lat": ..., "lng": ..., "radius_km": ...}
    found:      int (number of hits within the radius)
    results:    [{"id", "iata", "name", "distance_meters"}, ...]
                sorted by ascending distance (Typesense's `geo_distance_meters`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import typesense

COLLECTION_NAME = "airports"


def make_client() -> typesense.Client:
    api_key = os.environ.get("TYPESENSE_API_KEY", "xyz")
    return typesense.Client(
        {
            "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
            "api_key": api_key,
            "connection_timeout_seconds": 5,
        }
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Return airports within a radius of a reference coordinate, "
            "sorted by ascending distance."
        )
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="Reference latitude in decimal degrees.",
    )
    parser.add_argument(
        "--lng",
        type=float,
        required=True,
        help="Reference longitude in decimal degrees.",
    )
    parser.add_argument(
        "--radius-km",
        type=float,
        required=True,
        help="Radius around the reference point in kilometers.",
    )
    return parser.parse_args(argv)


def search(client: typesense.Client, lat: float, lng: float, radius_km: float) -> dict[str, Any]:
    # Radius filter: `location:(<lat>, <lng>, <radius> km)` (note the lat/lng
    # ORDER — NOT GeoJSON's [lon, lat]).
    # Sort by ascending great-circle distance to the same point.
    search_parameters = {
        "q": "*",
        "query_by": "iata",
        "filter_by": f"location:({lat}, {lng}, {radius_km} km)",
        "sort_by": f"location({lat}, {lng}):asc",
        "per_page": 250,
    }
    response = client.collections[COLLECTION_NAME].documents.search(search_parameters)

    # `response` may be a dict or, with some SDK versions, an object with
    # `.__dict__`. Normalize to a dict.
    if hasattr(response, "__dict__") and not isinstance(response, dict):
        response = vars(response)

    hits = response.get("hits", []) if isinstance(response, dict) else []
    results = []
    for hit in hits:
        # Hit may be a dict or an object; normalize.
        if hasattr(hit, "__dict__") and not isinstance(hit, dict):
            hit = vars(hit)

        doc = hit.get("document", {}) if isinstance(hit, dict) else {}
        if hasattr(doc, "__dict__") and not isinstance(doc, dict):
            doc = vars(doc)

        # `geo_distance_meters` is computed by Typesense; we MUST surface
        # that exact value rather than recomputing it ourselves. Typesense
        # returns it as a dict `{"<field>": <distance>}` where `<field>` is
        # the geopoint field used in the sort/filter (`location` here).
        geo = hit.get("geo_distance_meters") if isinstance(hit, dict) else None
        if not isinstance(geo, dict) or "location" not in geo:
            # Fallback: some SDK/Typesense versions surface it at top level.
            geo = doc.get("geo_distance_meters") if isinstance(doc, dict) else {}
        distance = geo.get("location", 0) if isinstance(geo, dict) else 0

        results.append(
            {
                "id": doc.get("id", ""),
                "iata": doc.get("iata", ""),
                "name": doc.get("name", ""),
                # `distance_meters` is reported by Typesense as a float in
                # meters; the spec requires an integer.
                "distance_meters": int(round(distance)),
            }
        )

    return {
        "reference": {"lat": lat, "lng": lng, "radius_km": radius_km},
        "found": len(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client = make_client()
    payload = search(client, args.lat, args.lng, args.radius_km)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
