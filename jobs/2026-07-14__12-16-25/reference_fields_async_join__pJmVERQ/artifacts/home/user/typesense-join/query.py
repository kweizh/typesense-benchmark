import argparse
import sys
import json
import os
import typesense

def main():
    parser = argparse.ArgumentParser(description="Query Typesense social likes graph")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--product', type=str, help='Product ID to find users who liked it')
    group.add_argument('--user', type=str, help='User ID to find products they liked')
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

    if args.product:
        usernames = []
        page = 1
        while True:
            search_params = {
                'q': '*',
                'filter_by': f'product_id:={args.product}',
                'include_fields': '$users(*)',
                'page': page,
                'per_page': 250
            }
            try:
                res = client.collections['likes'].documents.search(search_params)
            except Exception:
                break
            hits = res.get('hits', [])
            if not hits:
                break
            for hit in hits:
                doc = hit.get('document', {})
                user_info = doc.get('users')
                if user_info and 'username' in user_info:
                    usernames.append(user_info['username'])
            if len(hits) < 250:
                break
            page += 1
        unique_usernames = sorted(list(set(usernames)))
        print(json.dumps(unique_usernames))

    elif args.user:
        product_names = []
        page = 1
        while True:
            search_params = {
                'q': '*',
                'filter_by': f'user_id:={args.user}',
                'include_fields': '$products(*)',
                'page': page,
                'per_page': 250
            }
            try:
                res = client.collections['likes'].documents.search(search_params)
            except Exception:
                break
            hits = res.get('hits', [])
            if not hits:
                break
            for hit in hits:
                doc = hit.get('document', {})
                product_info = doc.get('products')
                if product_info and 'product_name' in product_info:
                    product_names.append(product_info['product_name'])
            if len(hits) < 250:
                break
            page += 1
        unique_products = sorted(list(set(product_names)))
        print(json.dumps(unique_products))

if __name__ == '__main__':
    main()
