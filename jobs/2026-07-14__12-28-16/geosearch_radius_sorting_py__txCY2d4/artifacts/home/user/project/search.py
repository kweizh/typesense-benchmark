#!/usr/bin/env python3
"""Search for airports within a radius of a reference coordinate.

Queries the `airports` Typesense collection, filtering by a geographic radius
and sorting the results by ascending great-circle distance from the reference
point.  The distance reported for each hit comes directly from Typesense's
``geo_distance_meters`` field (we do not recompute it).

Usage:
    python3 /home/user/project/search.py --lat <lat> --lng <lng> --radius-km <radius>

Output (stdout): a single JSON object with keys:
    reference   : {"lat", "lng", "radius_km"} echoing the query
    found       : int, number of airports within the radius
    results     : [{"id","iata","name","distance_meters"}, ...] sorted ascending
"""

import argparse
import json
import os
import sys

import typesense

# --- Configuration -----------------------------------------------------------

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECTION_NAME = "airports"

TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = 8108
TYPESENSE_PROTOCOL = "http"
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")


def get_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [
                {
                    "host": TYPESENSE_HOST,
                    "port": TYPESENSE_PORT,
                    "protocol": TYPESENSE_PROTOCOL,
                }
            ],
            "api_key": TYPESENSE_API_KEY,
            "connection_timeout_seconds": 10,
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find airports within a radius of a coordinate, sorted by distance."
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="Reference latitude (decimal degrees).",
    )
    parser.add_argument(
        "--lng",
        type=float,
        required=True,
        help="Reference longitude (decimal degrees).",
    )
    parser.add_argument(
        "--radius-km",
        type=float,
        required=True,
        help="Search radius in kilometers.",
    )
    return parser.parse_args()


def search_airports(lat: float, lng: float, radius_km: float) -> dict:
    """Run the geo radius search and return the formatted result object."""
    client = get_client()

    # filter_by: location:(lat, lng, <radius> km)
    # sort_by  : location(lat, lng):asc
    search_params = {
        "q": "*",
        "query_by": "name",  # required by Typesense even for * searches
        "filter_by": f"location:({lat}, {lng}, {radius_km} km)",
        "sort_by": f"location({lat}, {lng}):asc",
        # Return all matches within the radius (no pagination cap issues).
        "per_page": 250,
    }

    response = client.collections[COLLECTION_NAME].documents.search(search_params)

    hits = response.get("hits", [])

    results = []
    for hit in hits:
        doc = hit.get("document", {})
        # geo_distance_meters is keyed by the field name used for sorting.
        geo_dist = hit.get("geo_distance_meters", {})
        distance_meters = geo_dist.get("location")
        if distance_meters is None:
            # Fallback: some versions return the distance under the top-level
            # search metadata; if missing entirely skip the hit defensively.
            distance_meters = 0
        results.append(
            {
                "id": str(doc.get("id", "")),
                "iata": str(doc.get("iata", "")),
                "name": str(doc.get("name", "")),
                "distance_meters": int(round(distance_meters)),
            }
        )

    # The hits are already sorted by ascending distance by Typesense, but we
    # enforce the order explicitly so the output contract is guaranteed.
    results.sort(key=lambda r: r["distance_meters"])

    return {
        "reference": {
            "lat": lat,
            "lng": lng,
            "radius_km": radius_km,
        },
        "found": len(results),
        "results": results,
    }


def main() -> None:
    args = parse_args()
    try:
        output = search_airports(args.lat, args.lng, args.radius_km)
    except typesense.exceptions.ObjectNotFound:
        # Collection does not exist yet.
        print(
            json.dumps(
                {
                    "reference": {
                        "lat": args.lat,
                        "lng": args.lng,
                        "radius_km": args.radius_km,
                    },
                    "found": 0,
                    "results": [],
                }
            )
        )
        return
    except typesense.exceptions.TypesenseClientError as exc:
        print(f"Typesense search error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(output))


if __name__ == "__main__":
    main()