import os
import json
import argparse
import typesense

def main():
    parser = argparse.ArgumentParser(description="Search airports near a coordinate.")
    parser.add_argument("--lat", type=float, required=True, help="Latitude of the reference point")
    parser.add_argument("--lng", type=float, required=True, help="Longitude of the reference point")
    parser.add_argument("--radius-km", type=float, required=True, help="Radius in kilometers")
    
    args = parser.parse_args()
    
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
    
    # Query Typesense
    search_parameters = {
        'q': '*',
        'query_by': 'name',
        'filter_by': f'location:({args.lat}, {args.lng}, {args.radius_km} km)',
        'sort_by': f'location({args.lat}, {args.lng}):asc',
        'per_page': 250
    }
    
    try:
        search_result = client.collections['airports'].documents.search(search_parameters)
    except Exception as e:
        # If there's an error, we should output an empty result or handle it
        # But for this CLI, let's output a valid JSON representing 0 results or raise/print error.
        # It's better to raise or print clean JSON.
        # Let's print a valid empty response if the collection doesn't exist, or just crash if it's an unexpected error.
        # But if we did everything right, search should succeed.
        raise e
        
    hits = search_result.get('hits', [])
    
    results = []
    for hit in hits:
        doc = hit.get('document', {})
        geo_dist_obj = hit.get('geo_distance_meters', {})
        
        # geo_distance_meters is of the form {"location": <distance>}
        # Let's get the distance for the 'location' field
        distance_meters = geo_dist_obj.get('location')
        
        # In case it's an integer directly, or if 'location' is missing
        if isinstance(geo_dist_obj, int):
            distance_meters = geo_dist_obj
        elif distance_meters is None:
            distance_meters = 0
            
        results.append({
            'id': doc.get('id'),
            'iata': doc.get('iata'),
            'name': doc.get('name'),
            'distance_meters': int(distance_meters)
        })
        
    output = {
        'reference': {
            'lat': args.lat,
            'lng': args.lng,
            'radius_km': args.radius_km
        },
        'found': len(results),
        'results': results
    }
    
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
