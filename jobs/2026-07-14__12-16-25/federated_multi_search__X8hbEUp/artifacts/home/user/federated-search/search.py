import argparse
import os
import sys
import json
import urllib.parse
import requests

def main():
    parser = argparse.ArgumentParser(description="Federated Search")
    parser.add_argument("--query", required=True, help="The search query string")
    args = parser.parse_args()

    query = args.query

    TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "xyz")
    TYPESENSE_URL = "http://localhost:8108"

    headers = {
        "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
        "Content-Type": "application/json"
    }

    # We send queries in a specific order: products, articles, users
    collections = ["products", "articles", "users"]
    
    payload = {
        "searches": [
            {"collection": "products", "query_by": "product_name"},
            {"collection": "articles", "query_by": "title,body"},
            {"collection": "users", "query_by": "username,full_name"}
        ]
    }

    # Pass the shared query parameter `q` once as a common parameter in the URL
    url = f"{TYPESENSE_URL}/multi_search?q={urllib.parse.quote(query)}"

    output = {
        "query": query,
        "results": {}
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if res.status_code == 200:
            res_json = res.json()
            search_results = res_json.get("results", [])
            
            for idx, col_name in enumerate(collections):
                if idx < len(search_results):
                    col_res = search_results[idx]
                    # Check for partial failure in this slot
                    if "error" in col_res or ("code" in col_res and col_res.get("code") != 200):
                        err_msg = col_res.get("error", "Unknown sub-query error")
                        output["results"][col_name] = {"error": err_msg}
                    else:
                        found = col_res.get("found", 0)
                        hits = []
                        for hit in col_res.get("hits", []):
                            if "document" in hit:
                                hits.append(hit["document"])
                        output["results"][col_name] = {
                            "found": found,
                            "hits": hits
                        }
                else:
                    output["results"][col_name] = {"error": "No result returned for this collection"}
        else:
            err_msg = f"HTTP {res.status_code}: {res.text}"
            for col_name in collections:
                output["results"][col_name] = {"error": err_msg}

    except Exception as e:
        err_msg = str(e)
        for col_name in collections:
            output["results"][col_name] = {"error": err_msg}

    # Print the single JSON object to stdout
    print(json.dumps(output))
    sys.exit(0)

if __name__ == "__main__":
    main()
