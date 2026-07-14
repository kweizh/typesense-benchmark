import os
import json
import typesense

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
    
    # Drop existing collection if it exists
    print("Dropping existing collection 'airports' if it exists...")
    try:
        client.collections['airports'].delete()
        print("Collection 'airports' dropped.")
    except Exception as e:
        print(f"Collection 'airports' did not exist or could not be dropped: {e}")
        
    # Create the schema
    schema = {
        'name': 'airports',
        'fields': [
            {'name': 'name', 'type': 'string'},
            {'name': 'iata', 'type': 'string'},
            {'name': 'city', 'type': 'string'},
            {'name': 'country', 'type': 'string'},
            {'name': 'location', 'type': 'geopoint'}
        ]
    }
    
    print("Creating collection 'airports'...")
    client.collections.create(schema)
    print("Collection 'airports' created successfully.")
    
    # Load and parse data
    print("Reading data from /home/user/project/data/airports.jsonl...")
    documents = []
    with open('/home/user/project/data/airports.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            doc = {
                'id': data['id'],
                'name': data['name'],
                'iata': data['iata'],
                'city': data['city'],
                'country': data['country'],
                'location': [float(data['lat']), float(data['lng'])]
            }
            documents.append(doc)
            
    print(f"Loaded {len(documents)} documents. Importing into Typesense...")
    
    # Import into Typesense
    # Note: import_ can accept a list of dicts, or a JSONL string.
    # Passing a list of dicts is clean and supported by the python SDK.
    import_results = client.collections['airports'].documents.import_(documents, {'action': 'create'})
    
    # If import_results is a string (JSONL), we can parse it to check for errors.
    # If it's a list, we can also check for errors.
    errors = []
    if isinstance(import_results, str):
        # It's a JSONL string
        for line in import_results.split('\n'):
            if not line.strip():
                continue
            res = json.loads(line)
            if not res.get('success', True):
                errors.append(res)
    elif isinstance(import_results, list):
        for res in import_results:
            if not res.get('success', True):
                errors.append(res)
                
    if errors:
        print(f"Import completed with {len(errors)} errors:")
        for err in errors[:5]:
            print(err)
    else:
        print("Import completed successfully with no errors.")

if __name__ == '__main__':
    main()
