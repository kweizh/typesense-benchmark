import typesense
import os
import json
import time

def main():
    api_key = os.environ.get('TYPESENSE_API_KEY', 'xyz')
    client = typesense.Client({
      'nodes': [{
        'host': 'localhost',
        'port': '8108',
        'protocol': 'http'
      }],
      'api_key': api_key,
      'connection_timeout_seconds': 5
    })

    # Delete existing collections
    for col in ['likes', 'users', 'products']:
        try:
            client.collections[col].delete()
            print(f"Deleted collection: {col}")
        except Exception:
            pass

    # Define schemas
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
    print("Collections created.")

    # Likes to index
    likes_data = [
        {'id': 'l1', 'user_id': 'u1', 'product_id': 'p1'},
        {'id': 'l2', 'user_id': 'u1', 'product_id': 'p2'},
        {'id': 'l3', 'user_id': 'u2', 'product_id': 'p2'},
        {'id': 'l4', 'user_id': 'u3', 'product_id': 'p2'},
        {'id': 'l5', 'user_id': 'u2', 'product_id': 'p3'},
        {'id': 'l6', 'user_id': 'u4', 'product_id': 'p1'}
    ]

    print("Indexing likes first (before users/products exist)...")
    for like in likes_data:
        client.collections['likes'].documents.create(like)
    print("Likes indexed.")

    # Verify that they are indexed but references do not resolve
    print("Verifying references before users/products are indexed...")
    search_res = client.collections['likes'].documents.search({
        'q': '*',
        'include_fields': '$users(*),$products(*)'
    })
    for hit in search_res.get('hits', []):
        doc = hit['document']
        print(f"Like {doc['id']}: user_id={doc['user_id']} (resolved: {'users' in doc}), product_id={doc['product_id']} (resolved: {'products' in doc})")

    # Now index users and products
    users_data = [
        {'id': 'u1', 'username': 'alice'},
        {'id': 'u2', 'username': 'bob'},
        {'id': 'u3', 'username': 'charlie'},
        {'id': 'u4', 'username': 'david'}
    ]

    products_data = [
        {'id': 'p1', 'product_name': 'laptop'},
        {'id': 'p2', 'product_name': 'smartphone'},
        {'id': 'p3', 'product_name': 'headphones'}
    ]

    print("\nIndexing users...")
    for user in users_data:
        client.collections['users'].documents.create(user)

    print("Indexing products...")
    for prod in products_data:
        client.collections['products'].documents.create(prod)

    print("\nWaiting 2 seconds for asynchronous reference resolution to process...")
    time.sleep(2)

    # Verify that references have now resolved
    print("Verifying references after indexing users/products...")
    search_res = client.collections['likes'].documents.search({
        'q': '*',
        'include_fields': '$users(*),$products(*)'
    })
    all_resolved = True
    for hit in search_res.get('hits', []):
        doc = hit['document']
        resolved_u = 'users' in doc
        resolved_p = 'products' in doc
        print(f"Like {doc['id']}: user_id={doc['user_id']} (resolved: {resolved_u}), product_id={doc['product_id']} (resolved: {resolved_p})")
        if not (resolved_u and resolved_p):
            all_resolved = False

    if all_resolved:
        print("\nSuccess! All asynchronous references successfully resolved.")
    else:
        print("\nWarning: Some references did not resolve yet.")

if __name__ == '__main__':
    main()
