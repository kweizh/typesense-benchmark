import urllib.request
import json

def test_request(url, method, api_key, data=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8') if data else None,
        headers={
            "X-TYPESENSE-API-KEY": api_key,
            "Content-Type": "application/json" if data else "application/octet-stream"
        },
        method=method
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode('utf-8'))
        except Exception:
            err_body = "Could not parse error body"
        return e.code, err_body
    except Exception as e:
        return 0, str(e)

def main():
    # Load keys
    with open("/home/user/typesense-rbac/keys.json") as f:
        keys = json.load(f)
        
    search_only = keys["search_only"]
    products_writer = keys["products_writer"]
    admin = keys["admin"]
    
    results = []
    
    print("--- STARTING RBAC VERIFICATION ---")
    
    # 1. Test search_only key
    print("\nTesting 'search_only' key...")
    
    # Search products (Expected: Success)
    code, body = test_request("http://localhost:8108/collections/products/documents/search?q=*&query_by=title", "GET", search_only)
    results.append(("search_only - search products", code == 200, f"Expected 200, got {code}"))
    print(f"  Search products: {code} (Expected: 200)")
    
    # Search orders (Expected: Success)
    code, body = test_request("http://localhost:8108/collections/orders/documents/search?q=*&query_by=title", "GET", search_only)
    results.append(("search_only - search orders", code == 200, f"Expected 200, got {code}"))
    print(f"  Search orders: {code} (Expected: 200)")
    
    # Write to products (Expected: 401 or 403)
    code, body = test_request("http://localhost:8108/collections/products/documents", "POST", search_only, {"title": "Forbidden Product"})
    results.append(("search_only - write products", code in (401, 403), f"Expected 401/403, got {code}"))
    print(f"  Write products: {code} (Expected: 401/403)")
    
    # Write to orders (Expected: 401 or 403)
    code, body = test_request("http://localhost:8108/collections/orders/documents", "POST", search_only, {"title": "Forbidden Order"})
    results.append(("search_only - write orders", code in (401, 403), f"Expected 401/403, got {code}"))
    print(f"  Write orders: {code} (Expected: 401/403)")
    
    
    # 2. Test products_writer key
    print("\nTesting 'products_writer' key...")
    
    # Write to products (Expected: Success 201)
    code, body = test_request("http://localhost:8108/collections/products/documents", "POST", products_writer, {"title": "Writer Product"})
    results.append(("products_writer - write products", code == 201, f"Expected 201, got {code}"))
    print(f"  Write products: {code} (Expected: 201)")
    
    # Write to orders (Expected: 401 or 403)
    code, body = test_request("http://localhost:8108/collections/orders/documents", "POST", products_writer, {"title": "Forbidden Order"})
    results.append(("products_writer - write orders", code in (401, 403), f"Expected 401/403, got {code}"))
    print(f"  Write orders: {code} (Expected: 401/403)")
    
    # Search products (Expected: 401 or 403)
    code, body = test_request("http://localhost:8108/collections/products/documents/search?q=*&query_by=title", "GET", products_writer)
    results.append(("products_writer - search products", code in (401, 403), f"Expected 401/403, got {code}"))
    print(f"  Search products: {code} (Expected: 401/403)")
    
    
    # 3. Test admin key
    print("\nTesting 'admin' key...")
    
    # Search products (Expected: Success)
    code, body = test_request("http://localhost:8108/collections/products/documents/search?q=*&query_by=title", "GET", admin)
    results.append(("admin - search products", code == 200, f"Expected 200, got {code}"))
    print(f"  Search products: {code} (Expected: 200)")
    
    # Write to products (Expected: Success)
    code, body = test_request("http://localhost:8108/collections/products/documents", "POST", admin, {"title": "Admin Product"})
    results.append(("admin - write products", code == 201, f"Expected 201, got {code}"))
    print(f"  Write products: {code} (Expected: 201)")
    
    # Write to orders (Expected: Success)
    code, body = test_request("http://localhost:8108/collections/orders/documents", "POST", admin, {"title": "Admin Order"})
    results.append(("admin - write orders", code == 201, f"Expected 201, got {code}"))
    print(f"  Write orders: {code} (Expected: 201)")
    
    
    # Summary
    print("\n--- SUMMARY ---")
    all_passed = True
    for name, passed, detail in results:
        status = "PASSED" if passed else "FAILED"
        if not passed:
            all_passed = False
        print(f"[{status}] {name}: {detail}")
        
    if all_passed:
        print("\nALL TESTS PASSED! RBAC behavior works exactly as expected.")
    else:
        print("\nSOME TESTS FAILED.")
        exit(1)

if __name__ == "__main__":
    main()
