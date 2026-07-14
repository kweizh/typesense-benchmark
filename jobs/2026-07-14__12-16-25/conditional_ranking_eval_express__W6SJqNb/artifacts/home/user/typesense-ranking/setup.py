import typesense
from typesense.exceptions import ObjectNotFound

def main():
    client = typesense.Client({
        'api_key': 'xyz',
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'connection_timeout_seconds': 10
    })

    # Drop the collection if it exists
    try:
        client.collections['catalog'].delete()
        print("Deleted existing catalog collection.")
    except ObjectNotFound:
        print("Collection catalog does not exist yet.")
    except Exception as e:
        print(f"Error checking/deleting collection: {e}")

    # Define schema
    schema = {
        'name': 'catalog',
        'fields': [
            {'name': 'title', 'type': 'string'},
            {'name': 'description', 'type': 'string'},
            {'name': 'badge', 'type': 'string', 'facet': True},
            {'name': 'popularity', 'type': 'int32'}
        ]
    }

    # Create collection
    client.collections.create(schema)
    print("Created catalog collection.")

    # Documents to index
    documents = [
        {"id": "P1", "title": "Alpine Trek Boots", "description": "Alpine Trek ready footwear", "badge": "featured", "popularity": 10},
        {"id": "P2", "title": "Alpine Trek Jacket", "description": "Alpine Trek insulated layer", "badge": "featured", "popularity": 80},
        {"id": "P3", "title": "Alpine Trek Poles", "description": "Summit carbon poles", "badge": "sponsored", "popularity": 5},
        {"id": "P4", "title": "Alpine Trek Tent", "description": "Alpine Trek shelter system", "badge": "none", "popularity": 99},
        {"id": "P5", "title": "Alpine Trek Gloves", "description": "Summit winter gloves", "badge": "sponsored", "popularity": 40},
        {"id": "P6", "title": "Alpine Trek Socks", "description": "Merino wool socks", "badge": "featured", "popularity": 100}
    ]

    # Import documents
    result = client.collections['catalog'].documents.import_(documents, {'action': 'create'})
    print("Imported documents. Result:", result)

if __name__ == '__main__':
    main()
