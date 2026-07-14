import urllib.request
import urllib.error
import urllib.parse
import json
import time
import os

BASE_URL = "http://localhost:8108"
HEADERS = {
    "X-TYPESENSE-API-KEY": "xyz",
    "Content-Type": "application/json"
}

def make_request(path, method, data=None):
    # Properly encode spaces and other special characters in the URL path/query
    parts = path.split('?', 1)
    if len(parts) == 2:
        path_part, query_part = parts
        # Parse query params, quote them, and re-assemble
        query_params = urllib.parse.parse_qsl(query_part)
        encoded_query = urllib.parse.urlencode(query_params)
        url = f"{BASE_URL}{path_part}?{encoded_query}"
    else:
        url = f"{BASE_URL}{path}"

    req_data = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(url, data=req_data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        print(f"HTTP Error on {method} {path}: {e.code} - {err_msg}")
        raise Exception(f"Request failed: {err_msg}")

def wait_for_typesense():
    print("Waiting for Typesense server to be ready...")
    for i in range(10):
        try:
            res = make_request("/health", "GET")
            if res.get("ok"):
                print("Typesense is ready!")
                return
        except Exception:
            pass
        time.sleep(1)
    raise Exception("Typesense server not responding")

def main():
    wait_for_typesense()

    # 1. Create collection 'catalog'
    # Delete first if already exists
    try:
        make_request("/collections/catalog", "DELETE")
        print("Deleted existing catalog collection.")
    except Exception:
        pass

    schema = {
        "name": "catalog",
        "fields": [
            {"name": "name", "type": "string"},
            {"name": "brand", "type": "string", "facet": True},
            {"name": "category", "type": "string", "facet": True},
            {"name": "popularity", "type": "int32"}
        ],
        "default_sorting_field": "popularity"
    }
    
    print("Creating catalog collection...")
    col_res = make_request("/collections", "POST", schema)
    print("Collection created:", col_res["name"])

    # 2. Index documents
    documents = [
        {"id": "p1", "name": "Apple iPhone 15", "brand": "Apple", "category": "phone", "popularity": 50},
        {"id": "p2", "name": "Samsung Galaxy phone", "brand": "Samsung", "category": "phone", "popularity": 95},
        {"id": "p3", "name": "Google Pixel phone", "brand": "Google", "category": "phone", "popularity": 70},
        {"id": "p4", "name": "OnePlus 12 phone", "brand": "OnePlus", "category": "phone", "popularity": 30},
        {"id": "p5", "name": "Nokia Classic phone", "brand": "Nokia", "category": "phone", "popularity": 10},
        {"id": "p6", "name": "Refurbished phone deal", "brand": "Refurb", "category": "phone", "popularity": 5},
        {"id": "p7", "name": "Motorola Edge phone", "brand": "Motorola", "category": "phone", "popularity": 40}
    ]

    print("Indexing documents...")
    for doc in documents:
        doc_res = make_request("/collections/catalog/documents", "POST", doc)
        print(f"Indexed document {doc_res['id']}")

    # 3. Create overrides
    # Rule 1: Exact match on 'phone'
    override_phone = {
        "rule": {
            "query": "phone",
            "match": "exact"
        },
        "includes": [
            {"id": "p1", "position": 1},
            {"id": "p7", "position": 2}
        ],
        "excludes": [
            {"id": "p2"}
        ]
    }
    print("Creating override-phone rule...")
    make_request("/collections/catalog/overrides/override-phone", "PUT", override_phone)

    # Rule 2: Contains match on 'deal'
    override_deal = {
        "rule": {
            "query": "deal",
            "match": "contains"
        },
        "includes": [
            {"id": "p3", "position": 1}
        ]
    }
    print("Creating override-deal rule...")
    make_request("/collections/catalog/overrides/override-deal", "PUT", override_deal)

    # Rule 3: Dynamic brand filter
    override_brand = {
        "rule": {
            "query": "{brand} phone",
            "match": "contains"
        },
        "filter_by": "brand:={brand}",
        "remove_matched_tokens": True
    }
    print("Creating override-brand rule...")
    make_request("/collections/catalog/overrides/override-brand", "PUT", override_brand)

    # 4. Verify curation rules
    print("\n--- Verifying Curation Rule 1: Exact match on 'phone' ---")
    # Query: phone (exact)
    # Expected: p1 at pos 1, p7 at pos 2, p2 excluded.
    search_phone = make_request("/collections/catalog/documents/search?q=phone&query_by=name&sort_by=popularity:desc", "GET")
    hits_phone = [hit["document"]["id"] for hit in search_phone.get("hits", [])]
    print("Search query 'phone' hits:", hits_phone)
    assert hits_phone[0] == "p1", f"Expected p1 at position 1, got {hits_phone[0]}"
    assert hits_phone[1] == "p7", f"Expected p7 at position 2, got {hits_phone[1]}"
    assert "p2" not in hits_phone, "p2 should be excluded from search results"
    print("Rule 1 verified successfully!")

    print("\n--- Verifying Curation Rule 2: Contains match on 'deal' ---")
    # Query: cheap phone deal
    # Expected: p3 at pos 1
    search_deal = make_request("/collections/catalog/documents/search?q=cheap phone deal&query_by=name&sort_by=popularity:desc", "GET")
    hits_deal = [hit["document"]["id"] for hit in search_deal.get("hits", [])]
    print("Search query 'cheap phone deal' hits:", hits_deal)
    assert hits_deal[0] == "p3", f"Expected p3 at position 1, got {hits_deal[0]}"
    print("Rule 2 verified successfully!")

    print("\n--- Verifying Curation Rule 3: Dynamic brand filter ---")
    # Query: Apple phone
    # Expected: Only Apple brand phone (p1). Samsung (p2), etc. should be filtered out.
    search_brand = make_request("/collections/catalog/documents/search?q=Apple phone&query_by=name&sort_by=popularity:desc", "GET")
    hits_brand = [hit["document"]["id"] for hit in search_brand.get("hits", [])]
    print("Search query 'Apple phone' hits:", hits_brand)
    for hit in search_brand.get("hits", []):
        doc = hit["document"]
        assert doc["brand"] == "Apple", f"Expected only Apple products, got {doc['brand']} (id: {doc['id']})"
    print("Rule 3 verified successfully!")

    # 5. Write the setup.log file
    log_path = "/home/user/typesense-curation/setup.log"
    print(f"\nWriting override IDs to {log_path}...")
    with open(log_path, "w") as f:
        f.write("override-phone\n")
        f.write("override-deal\n")
        f.write("override-brand\n")
    print("Setup log written successfully.")

if __name__ == "__main__":
    main()
