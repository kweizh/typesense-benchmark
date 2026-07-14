#!/usr/bin/env python3
"""
search.py – Geo-radius airport search backed by Typesense.

Usage:
    TYPESENSE_API_KEY=xyz python3 search.py \
        --lat <lat> --lng <lng> --radius-km <km>

Prints a single JSON object to stdout:
{
  "reference": {"lat": ..., "lng": ..., "radius_km": ...},
  "found": <int>,
  "results": [
    {"id": "...", "iata": "...", "name": "...", "distance_meters": <int>},
    ...
  ]
}
Results are sorted by ascending distance (Typesense handles the ordering).
Only airports within the specified radius are included.
"""

import argparse
import json
import os
import sys

import typesense

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
COLLECTION_NAME = "airports"

client = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": API_KEY,
        "connection_timeout_seconds": 10,
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search airports within a geo radius using Typesense."
    )
    parser.add_argument("--lat",       type=float, required=True,  help="Reference latitude")
    parser.add_argument("--lng",       type=float, required=True,  help="Reference longitude")
    parser.add_argument("--radius-km", type=float, required=True,  help="Search radius in kilometres")
    return parser.parse_args()


def search_airports(lat: float, lng: float, radius_km: float) -> list[dict]:
    """
    Query Typesense for airports within radius_km of (lat, lng).
    Returns a list of hit dicts with id, iata, name, distance_meters.
    """
    # Use a large per_page to retrieve all matching airports in one call.
    # The dataset is small (20 records), but 250 is a safe upper bound.
    search_params = {
        "q":          "*",
        "query_by":   "name",           # required field for Typesense, wildcard query ignores it
        "filter_by":  f"location:({lat}, {lng}, {radius_km} km)",
        "sort_by":    f"location({lat}, {lng}):asc",
        "per_page":   250,
        "include_fields": "id,iata,name,location",
    }

    response = client.collections[COLLECTION_NAME].documents.search(search_params)

    hits = []
    for hit in response.get("hits", []):
        doc = hit["document"]
        # Typesense reports per-hit geo distance in the geo_distance_meters dict,
        # keyed by the field name.
        geo_distances = hit.get("geo_distance_meters", {})
        distance_m = geo_distances.get("location", 0)
        hits.append(
            {
                "id":               doc["id"],
                "iata":             doc["iata"],
                "name":             doc["name"],
                "distance_meters":  int(distance_m),
            }
        )
    return hits


def main() -> None:
    args = parse_args()
    lat       = args.lat
    lng       = args.lng
    radius_km = args.radius_km

    results = search_airports(lat, lng, radius_km)

    output = {
        "reference": {
            "lat":       lat,
            "lng":       lng,
            "radius_km": radius_km,
        },
        "found":   len(results),
        "results": results,
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
