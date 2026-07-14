import argparse
import json
import typesense
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', required=True, help='The search query')
    args = parser.parse_args()

    client = typesense.Client({
        'api_key': 'xyz',
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'connection_timeout_seconds': 10
    })

    search_parameters = {
        'q': args.query,
        'query_by': 'title,description',
        'text_match_type': 'sum_score',
        'sort_by': '_eval([(badge:sponsored):3, (badge:featured):2, (badge:none):1]):desc,_text_match:desc,popularity:desc'
    }

    try:
        res = client.collections['catalog'].documents.search(search_parameters)
        ids = [hit['document']['id'] for hit in res.get('hits', [])]
        print(json.dumps(ids))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
