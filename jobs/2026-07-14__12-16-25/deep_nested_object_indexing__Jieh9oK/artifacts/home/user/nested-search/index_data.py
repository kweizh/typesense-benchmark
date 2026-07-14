import json
import requests

url_collections = "http://localhost:8108/collections"
headers = {
    "X-TYPESENSE-API-KEY": "xyz",
    "Content-Type": "application/json"
}

# 1. Define schema
schema = {
    "name": "nested_orders",
    "enable_nested_fields": True,
    "fields": [
        {"name": "orders", "type": "object[]", "optional": True},
        {"name": "orders.line_items", "type": "object[]", "optional": True},
        {"name": "orders.line_items.name", "type": "string[]", "optional": True},
        {"name": "orders.line_items.category", "type": "string[]", "optional": True, "facet": True},
        {"name": "orders.line_items.attributes", "type": "object[]", "optional": True},
        {"name": "orders.line_items.attributes.color", "type": "string[]", "optional": True}
    ]
}

# Delete collection if it exists
requests.delete("http://localhost:8108/collections/nested_orders", headers=headers)

# Create collection
r = requests.post(url_collections, headers=headers, data=json.dumps(schema))
print("Create collection response:", r.status_code, r.text)
if r.status_code != 201:
    raise Exception("Failed to create collection")

# 2. Index documents from orders.jsonl
import_url = "http://localhost:8108/collections/nested_orders/documents/import?action=create"
documents = []
with open("/home/user/nested-search/data/orders.jsonl", "r") as f:
    for line in f:
        line = line.strip()
        if line:
            documents.append(json.loads(line))

# We can import them one by one or using the import endpoint (JSONL format)
import_data = "\n".join(json.dumps(doc) for doc in documents)
r_import = requests.post(import_url, headers=headers, data=import_data)
print("Import response:", r_import.status_code, r_import.text)
