import os
import sys
import typesense

def main():
    api_key = os.environ.get("TYPESENSE_API_KEY")
    if not api_key:
        print("Error: TYPESENSE_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = typesense.Client({
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'api_key': api_key,
        'connection_timeout_seconds': 5
    })

    # Delete 'hubs' collection if it already exists
    try:
        client.collections['hubs'].delete()
        print("Deleted existing 'hubs' collection.")
    except Exception as e:
        # Collection might not exist, which is fine
        pass

    # Define schema
    schema = {
        'name': 'hubs',
        'fields': [
            {'name': 'name', 'type': 'string'},
            {'name': 'status', 'type': 'string', 'facet': True},
            {'name': 'location', 'type': 'geopoint'}
        ]
    }

    # Create collection
    try:
        client.collections.create(schema)
        print("Created 'hubs' collection schema.")
    except Exception as e:
        print(f"Error creating collection: {e}", file=sys.stderr)
        sys.exit(1)

    # Hub Dataset
    documents = [
        {"id": "h01", "name": "Alpha", "status": "active", "location": [37.78, -122.42]},
        {"id": "h02", "name": "Bravo", "status": "active", "location": [37.79, -122.42]},
        {"id": "h03", "name": "Charlie", "status": "active", "location": [37.81, -122.42]},
        {"id": "h04", "name": "Delta", "status": "active", "location": [37.78, -122.46]},
        {"id": "h05", "name": "Echo", "status": "active", "location": [37.78, -122.38]},
        {"id": "h06", "name": "Foxtrot", "status": "active", "location": [37.73, -122.42]},
        {"id": "h07", "name": "Golf", "status": "active", "location": [37.77, -122.432]},
        {"id": "h08", "name": "Hotel", "status": "active", "location": [37.77, -122.438]},
        {"id": "h09", "name": "India", "status": "maintenance", "location": [37.775, -122.42]},
        {"id": "h10", "name": "Juliet", "status": "maintenance", "location": [37.785, -122.415]}
    ]

    # Import documents
    try:
        results = client.collections['hubs'].documents.import_(documents, {'action': 'upsert'})
        # Verify if any import failed
        failed = [res for res in results if not res.get('success', True)]
        if failed:
            print(f"Failed to import some documents: {failed}", file=sys.stderr)
            sys.exit(1)
        print(f"Successfully seeded {len(documents)} hubs.")
    except Exception as e:
        print(f"Error importing documents: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
