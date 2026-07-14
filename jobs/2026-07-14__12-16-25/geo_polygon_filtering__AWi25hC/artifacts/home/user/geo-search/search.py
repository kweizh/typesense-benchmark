import argparse
import json
import os
import sys
import typesense

def main():
    parser = argparse.ArgumentParser(description="Typesense Geo-Polygon Search CLI")
    parser.add_argument("--polygon", required=True, help="Comma-separated string of alternating lat/lng values")
    parser.add_argument("--exclude-status", help="Optional status value to exclude from results")
    args = parser.parse_args()

    # Retrieve API key
    api_key = os.environ.get("TYPESENSE_API_KEY")
    if not api_key:
        print("Error: TYPESENSE_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Parse polygon coordinates
    polygon_str = args.polygon.strip(' "<>()[]')
    parts = [p.strip() for p in polygon_str.split(',') if p.strip()]

    coords = []
    for p in parts:
        try:
            coords.append(float(p))
        except ValueError:
            print(f"Error: Invalid coordinate value '{p}'", file=sys.stderr)
            sys.exit(1)

    if len(coords) % 2 != 0:
        print("Error: Polygon must have an even number of coordinate values (alternating lat, lng).", file=sys.stderr)
        sys.exit(1)

    if len(coords) < 6:
        print("Error: Polygon must have at least 3 vertices (6 coordinate values).", file=sys.stderr)
        sys.exit(1)

    # Initialize Typesense client
    client = typesense.Client({
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'api_key': api_key,
        'connection_timeout_seconds': 5
    })

    # Construct filter_by expression
    filter_by = f"location:({', '.join(str(c) for c in coords)})"
    if args.exclude_status:
        filter_by += f" && status:!={args.exclude_status}"

    try:
        # Search hubs
        # We set per_page to 100 to ensure we get all matching hubs (the dataset has 10 hubs)
        res = client.collections['hubs'].documents.search({
            'q': '*',
            'query_by': 'name',
            'filter_by': filter_by,
            'per_page': 100
        })

        # Extract hub IDs
        hub_ids = [h['document']['id'] for h in res.get('hits', [])]
        # Sort in ascending lexicographic order
        hub_ids.sort()

        # Print JSON output to stdout
        print(json.dumps({"hub_ids": hub_ids}))

    except Exception as e:
        print(f"Error executing search: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
