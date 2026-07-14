#!/usr/bin/env python3
import json
import os
import typesense

def main():
    client = typesense.Client({
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'api_key': 'xyz',
        'connection_timeout_seconds': 5
    })

    # Delete collection if it exists
    try:
        client.collections['products'].delete()
        print("Deleted existing 'products' collection.")
    except Exception as e:
        # If it doesn't exist, ignore
        pass

    # Create collection schema
    schema = {
        'name': 'products',
        'fields': [
            {'name': 'product_name', 'type': 'string'},
            {'name': 'brand', 'type': 'string', 'facet': True},
            {'name': 'category', 'type': 'string', 'facet': True},
            {'name': 'tags', 'type': 'string[]', 'facet': True},
            {'name': 'price', 'type': 'float', 'facet': True},
            {'name': 'rating', 'type': 'float'}
        ]
    }

    client.collections.create(schema)
    print("Created 'products' collection.")

    # Load and index data
    dataset_path = '/home/user/facet-nav/data/products.jsonl'
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset not found at {dataset_path}")
        return

    documents = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                documents.append(json.loads(line))

    if documents:
        # Import documents
        import_results = client.collections['products'].documents.import_(documents, {'action': 'upsert'})
        print(f"Imported {len(documents)} documents.")
        # Print any error logs if present
        for res in import_results:
            if not res.get('success', True):
                print(f"Import error: {res}")
    else:
        print("No documents found to import.")

if __name__ == '__main__':
    main()
