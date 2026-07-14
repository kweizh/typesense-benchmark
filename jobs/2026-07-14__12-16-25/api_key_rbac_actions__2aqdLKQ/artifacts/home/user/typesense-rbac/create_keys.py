import urllib.request
import json

def create_key(description, actions, collections):
    url = "http://localhost:8108/keys"
    data = {
        "description": description,
        "actions": actions,
        "collections": collections
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={
            "X-TYPESENSE-API-KEY": "xyz",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print(f"Successfully created key: {description}")
            return res_data
    except Exception as e:
        print(f"Error creating key: {description}")
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'))
        raise e

def main():
    # 1. Search-only key
    search_only_res = create_key(
        description="Search-only key",
        actions=["documents:search"],
        collections=["*"]
    )
    
    # 2. Documents-write key
    products_writer_res = create_key(
        description="Write documents to products collection",
        actions=["documents:create", "documents:upsert", "documents:import"],
        collections=["products"]
    )
    
    # 3. Admin key
    admin_res = create_key(
        description="Admin key",
        actions=["*"],
        collections=["*"]
    )
    
    # Extract key values
    keys_data = {
        "search_only": search_only_res["value"],
        "products_writer": products_writer_res["value"],
        "admin": admin_res["value"]
    }
    
    # Write to keys.json
    output_path = "/home/user/typesense-rbac/keys.json"
    with open(output_path, "w") as f:
        json.dump(keys_data, f, indent=2)
    print(f"Successfully wrote keys to {output_path}")

if __name__ == "__main__":
    main()
