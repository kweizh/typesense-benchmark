import os
import sys
import json
import requests

TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "xyz")
TYPESENSE_URL = "http://localhost:8108"

headers = {
    "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
    "Content-Type": "application/json"
}

schemas = {
    "products": {
        "name": "products",
        "fields": [
            {"name": "product_name", "type": "string"},
            {"name": "category", "type": "string", "facet": True},
            {"name": "price", "type": "float"}
        ]
    },
    "articles": {
        "name": "articles",
        "fields": [
            {"name": "title", "type": "string"},
            {"name": "body", "type": "string"},
            {"name": "author", "type": "string"}
        ]
    },
    "users": {
        "name": "users",
        "fields": [
            {"name": "username", "type": "string"},
            {"name": "full_name", "type": "string"},
            {"name": "bio", "type": "string"}
        ]
    }
}

data_files = {
    "products": "/home/user/federated-search/data/products.jsonl",
    "articles": "/home/user/federated-search/data/articles.jsonl",
    "users": "/home/user/federated-search/data/users.jsonl"
}

def setup_collections():
    for name, schema in schemas.items():
        # Step 1: Check if collection exists and delete it
        url = f"{TYPESENSE_URL}/collections/{name}"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            print(f"Collection '{name}' already exists. Deleting it for idempotency...")
            del_res = requests.delete(url, headers=headers)
            if del_res.status_code != 200:
                print(f"Failed to delete collection '{name}': {del_res.text}")
                sys.exit(1)
            print(f"Collection '{name}' deleted successfully.")

        # Step 2: Create collection
        create_url = f"{TYPESENSE_URL}/collections"
        print(f"Creating collection '{name}'...")
        create_res = requests.post(create_url, headers=headers, json=schema)
        if create_res.status_code not in (200, 201):
            print(f"Failed to create collection '{name}': {create_res.text}")
            sys.exit(1)
        print(f"Collection '{name}' created successfully.")

        # Step 3: Import data
        filepath = data_files[name]
        if not os.path.exists(filepath):
            print(f"Data file not found: {filepath}")
            sys.exit(1)

        print(f"Importing data for '{name}' from {filepath}...")
        with open(filepath, "r", encoding="utf-8") as f:
            import_data = f.read()

        import_url = f"{TYPESENSE_URL}/collections/{name}/documents/import?action=create"
        import_res = requests.post(import_url, headers=headers, data=import_data.encode("utf-8"))
        if import_res.status_code not in (200, 201):
            print(f"Failed to import data for '{name}': {import_res.text}")
            sys.exit(1)
        
        # Verify if there were errors in the import response (JSONL response)
        # Each line in the import response corresponds to a document import result
        lines = import_res.text.strip().split("\n")
        has_errors = False
        for line in lines:
            if not line:
                continue
            try:
                res_obj = json.loads(line)
                if not res_obj.get("success", True):
                    print(f"Import error: {res_obj}")
                    has_errors = True
            except Exception as e:
                print(f"Error parsing import result line: {line}. Error: {e}")
                has_errors = True
        
        if has_errors:
            print(f"Some documents failed to import for '{name}'.")
            sys.exit(1)

        print(f"Data for '{name}' imported successfully.")

if __name__ == "__main__":
    setup_collections()
    print("Typesense provisioning completed successfully.")
