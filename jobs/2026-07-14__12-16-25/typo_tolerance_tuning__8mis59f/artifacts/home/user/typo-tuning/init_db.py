import typesense
import json

client = typesense.Client({
  'nodes': [{
    'host': 'localhost',
    'port': '8108',
    'protocol': 'http'
  }],
  'api_key': 'xyz',
  'connection_timeout_seconds': 2
})

# Delete collection if it exists
try:
    client.collections['catalog'].delete()
    print("Deleted existing 'catalog' collection.")
except Exception as e:
    pass

schema = {
  'name': 'catalog',
  'fields': [
    {'name': 'name', 'type': 'string'},
    {'name': 'brand', 'type': 'string'}
  ]
}

client.collections.create(schema)
print("Created 'catalog' collection.")

# Load products
with open('/home/user/typo-tuning/products.jsonl', 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        client.collections['catalog'].documents.create(doc)

print("Collection created and indexed successfully.")
