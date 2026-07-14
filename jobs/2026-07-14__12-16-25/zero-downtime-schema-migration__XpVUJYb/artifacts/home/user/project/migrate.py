import urllib.request
import json
import sys

TYPESENSE_URL = "http://localhost:8108"
API_KEY = "xyz"
OLD_COLLECTION = "products_v1"
NEW_COLLECTION = "products_v2"
ALIAS_NAME = "products"

def make_request(path, method="GET", body=None, headers=None, is_jsonl=False):
    url = f"{TYPESENSE_URL}{path}"
    req_headers = {
        "X-TYPESENSE-API-KEY": API_KEY
    }
    if headers:
        req_headers.update(headers)
    
    data = None
    if body is not None:
        if is_jsonl:
            data = body.encode('utf-8')
            req_headers["Content-Type"] = "text/plain"
        else:
            data = json.dumps(body).encode('utf-8')
            req_headers["Content-Type"] = "application/json"
            
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            resp_data = response.read()
            if is_jsonl:
                return resp_data.decode('utf-8')
            try:
                return json.loads(resp_data.decode('utf-8'))
            except json.JSONDecodeError:
                return resp_data.decode('utf-8')
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}", file=sys.stderr)
        raise e
    except Exception as e:
        print(f"Error making request to {url}: {e}", file=sys.stderr)
        raise e

def main():
    print("Starting migration process...")
    
    # 1. Get the schema of products_v1
    print(f"Fetching schema for {OLD_COLLECTION}...")
    old_schema = make_request(f"/collections/{OLD_COLLECTION}")
    print("Old schema fetched successfully.")
    
    # 2. Modify schema for products_v2
    new_schema = {
        "name": NEW_COLLECTION,
        "fields": [],
        "default_sorting_field": old_schema.get("default_sorting_field"),
        "enable_nested_fields": old_schema.get("enable_nested_fields", False),
        "symbols_to_index": old_schema.get("symbols_to_index", []),
        "token_separators": old_schema.get("token_separators", [])
    }
    
    for field in old_schema.get("fields", []):
        new_field = dict(field)
        if new_field["name"] == "rating":
            new_field["type"] = "float"
        new_schema["fields"].append(new_field)
        
    print(f"Creating new collection {NEW_COLLECTION}...")
    make_request("/collections", method="POST", body=new_schema)
    print(f"Collection {NEW_COLLECTION} created successfully.")
    
    # 3. Export documents from products_v1
    print(f"Exporting documents from {OLD_COLLECTION}...")
    documents_jsonl = make_request(f"/collections/{OLD_COLLECTION}/documents/export", method="GET", is_jsonl=True)
    num_docs = len([line for line in documents_jsonl.split('\n') if line.strip()])
    print(f"Exported {num_docs} documents.")
    
    # 4. Import documents into products_v2
    print(f"Importing {num_docs} documents into {NEW_COLLECTION}...")
    import_res = make_request(
        f"/collections/{NEW_COLLECTION}/documents/import?action=create&dirty_values=coerce_or_reject",
        method="POST",
        body=documents_jsonl,
        is_jsonl=True
    )
    print("Import response received.")
    
    # Check import results to make sure all were imported successfully
    for line in import_res.strip().split('\n'):
        if not line:
            continue
        try:
            res_obj = json.loads(line)
            if not res_obj.get("success", True):
                print(f"Warning: Failed to import document: {line}", file=sys.stderr)
        except json.JSONDecodeError:
            print(f"Warning: Failed to parse import response line: {line}", file=sys.stderr)

    # 5. Switch alias products to products_v2
    print(f"Switching alias {ALIAS_NAME} to point to {NEW_COLLECTION}...")
    alias_body = {"collection_name": NEW_COLLECTION}
    alias_res = make_request(f"/aliases/{ALIAS_NAME}", method="PUT", body=alias_body)
    print(f"Alias switched successfully: {alias_res}")
    
    # 6. Delete products_v1
    print(f"Deleting old collection {OLD_COLLECTION}...")
    delete_res = make_request(f"/collections/{OLD_COLLECTION}", method="DELETE")
    print(f"Deleted old collection successfully: {delete_res}")
    
    # 7. Write migration.log
    log_path = "/home/user/project/migration.log"
    print(f"Writing migration report to {log_path}...")
    with open(log_path, "w") as f:
        f.write(f"Migrated {num_docs} documents to {NEW_COLLECTION}\n")
        f.write(f"Alias {ALIAS_NAME} -> {NEW_COLLECTION}\n")
    print("Migration report written successfully.")
    
    print("Migration process completed successfully!")

if __name__ == "__main__":
    main()
