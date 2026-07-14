import argparse
import json
import requests
import sys

def main():
    parser = argparse.ArgumentParser(description="Query nested orders collection in Typesense.")
    parser.add_argument("--keyword", required=True, help="Keyword to search in product names.")
    parser.add_argument("--color", required=True, help="Color to filter by.")
    args = parser.parse_args()

    headers = {
        "X-TYPESENSE-API-KEY": "xyz"
    }

    matched_ids = []
    category_facet_counts = {}
    page = 1

    while True:
        params = {
            "q": args.keyword,
            "query_by": "orders.line_items.name",
            "filter_by": f"orders.line_items.attributes.color:={args.color}",
            "facet_by": "orders.line_items.category",
            "page": page,
            "per_page": 250
        }

        try:
            r = requests.get(
                "http://localhost:8108/collections/nested_orders/documents/search",
                headers=headers,
                params=params,
                timeout=10
            )
            r.raise_for_status()
            res = r.json()
        except Exception as e:
            # If there's an error, we should print a valid JSON or handle it gracefully.
            # But normally the server is running and healthy.
            sys.exit(f"Error querying Typesense: {e}")

        # Collect matched customer IDs
        hits = res.get("hits", [])
        for hit in hits:
            doc_id = hit["document"]["id"]
            if doc_id not in matched_ids:
                matched_ids.append(doc_id)

        # Collect facet counts from the first page response
        if page == 1 and "facet_counts" in res:
            for fc in res["facet_counts"]:
                if fc["field_name"] == "orders.line_items.category":
                    for c in fc["counts"]:
                        category_facet_counts[c["value"]] = c["count"]

        # Check if we need to fetch more pages
        # Typesense returns 'found' which is the total number of matching documents
        found = res.get("found", 0)
        if len(matched_ids) >= found or len(hits) < 250:
            break

        page += 1

    # Sort matched customer IDs lexicographically
    matched_ids_sorted = sorted(matched_ids)

    # Prepare output
    output = {
        "matched_customer_ids": matched_ids_sorted,
        "category_facet_counts": category_facet_counts
    }

    # Print exactly one JSON object to stdout
    print(json.dumps(output))

if __name__ == "__main__":
    main()
