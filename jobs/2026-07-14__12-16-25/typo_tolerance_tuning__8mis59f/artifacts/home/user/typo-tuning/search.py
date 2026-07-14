import sys
import argparse
import json
import typesense

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--q', required=True)
    args = parser.parse_args()

    client = typesense.Client({
      'nodes': [{
        'host': 'localhost',
        'port': '8108',
        'protocol': 'http'
      }],
      'api_key': 'xyz',
      'connection_timeout_seconds': 2
    })

    # Fixed search parameters matching all behavioral rules
    search_parameters = {
        'q': args.q,
        'query_by': 'name,brand',
        'prefix': 'false',
        'num_typos': '2,0',
        'min_len_1typo': 4,
        'min_len_2typo': 6,
        'drop_tokens_threshold': 1,
        'typo_tokens_threshold': 1,
        'split_join_tokens': 'always',
        'drop_tokens_mode': 'both_sides:3'
    }

    try:
        results = client.collections['catalog'].documents.search(search_parameters)
        ids = [hit['document']['id'] for hit in results.get('hits', [])]
        print(json.dumps(ids))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
