import typesense
import os
import json
import time

client = typesense.Client({
  'nodes': [{
    'host': 'localhost',
    'port': '8108',
    'protocol': 'http'
  }],
  'api_key': os.environ.get('TYPESENSE_API_KEY', 'xyz'),
  'connection_timeout_seconds': 5
})

# Delete existing collections if any
for col in ['likes', 'users', 'products']:
    try:
        client.collections[col].delete()
        print(f"Deleted collection: {col}")
    except Exception as e:
        print(f"Collection {col} did not exist or could not be deleted: {e}")

# Create collections
user_schema = {
    'name': 'users',
    'fields': [
        {'name': 'username', 'type': 'string'}
    ]
}

product_schema = {
    'name': 'products',
    'fields': [
        {'name': 'product_name', 'type': 'string'}
    ]
}

likes_schema = {
    'name': 'likes',
    'fields': [
        {
            'name': 'user_id',
            'type': 'string',
            'reference': 'users.id',
            'optional': True,
            'async_reference': True
        },
        {
            'name': 'product_id',
            'type': 'string',
            'reference': 'products.id',
            'optional': True,
            'async_reference': True
        }
    ]
}

print("Creating collections...")
client.collections.create(user_schema)
client.collections.create(product_schema)
client.collections.create(likes_schema)
print("Collections created successfully.")

# Index a like document first (before referenced user and product exist)
like_doc = {
    'id': 'like1',
    'user_id': 'user1',
    'product_id': 'product1'
}
print("Indexing like document before user and product exist...")
res = client.collections['likes'].documents.create(like_doc)
print("Like indexing result:", res)

# Try querying likes with join before user/product exist
query = {
    'q': '*',
    'filter_by': 'product_id:=product1',
    'include_fields': '$users(*)'
}
print("Querying likes before user/product exist...")
search_res = client.collections['likes'].documents.search(query)
print("Search result:", json.dumps(search_res, indent=2))

# Now index the user and product
print("Indexing user and product...")
client.collections['users'].documents.create({'id': 'user1', 'username': 'alice'})
client.collections['products'].documents.create({'id': 'product1', 'product_name': 'laptop'})

# Wait a short moment for async reference resolution to process
time.sleep(2)

print("Querying likes after user/product are indexed...")
search_res = client.collections['likes'].documents.search(query)
print("Search result:", json.dumps(search_res, indent=2))
