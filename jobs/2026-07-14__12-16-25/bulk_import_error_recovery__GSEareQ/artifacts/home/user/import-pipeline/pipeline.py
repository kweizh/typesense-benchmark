import json
import os
import requests
import typesense

def main():
    # 1. Initialize Typesense client
    client = typesense.Client({
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'api_key': 'xyz',
        'connection_timeout_seconds': 5
    })

    # 2. Recreate collection for idempotency
    collection_name = 'catalog'
    try:
        client.collections[collection_name].delete()
        print(f"Deleted existing '{collection_name}' collection.")
    except Exception:
        pass

    schema = {
        'name': collection_name,
        'fields': [
            {'name': 'sku', 'type': 'string'},
            {'name': 'name', 'type': 'string'},
            {'name': 'price', 'type': 'float'},
            {'name': 'quantity', 'type': 'int32'},
            {'name': 'category', 'type': 'string'}
        ]
    }
    client.collections.create(schema)
    print(f"Created '{collection_name}' collection with strict schema.")

    # 3. Read raw products dataset
    dataset_path = '/home/user/import-pipeline/data/raw_products.jsonl'
    with open(dataset_path, 'r', encoding='utf-8') as f:
        raw_docs = [json.loads(line) for line in f if line.strip()]

    total_docs = len(raw_docs)
    print(f"Loaded {total_docs} documents from {dataset_path}.")

    # 4. First-pass import
    import_url = f"http://localhost:8108/collections/{collection_name}/documents/import"
    import_params = {
        'action': 'create',
        'dirty_values': 'coerce_or_reject'
    }
    import_headers = {
        'X-TYPESENSE-API-KEY': 'xyz',
        'Content-Type': 'application/octet-stream'
    }

    raw_jsonl_bytes = '\n'.join(json.dumps(doc) for doc in raw_docs).encode('utf-8')
    response_first = requests.post(
        import_url,
        params=import_params,
        headers=import_headers,
        data=raw_jsonl_bytes
    )

    if response_first.status_code != 200:
        print(f"Error: First pass import returned status code {response_first.status_code}")
        print(response_first.text)
        return

    lines_first = response_first.text.strip().split('\n')
    
    imported_first_pass = []
    failed_first_pass = []  # list of (index, doc, error_message)

    for i, line in enumerate(lines_first):
        res = json.loads(line)
        if res.get('success'):
            imported_first_pass.append(raw_docs[i])
        else:
            failed_first_pass.append((i, raw_docs[i], res.get('error', '')))

    print(f"First-pass import: {len(imported_first_pass)} succeeded, {len(failed_first_pass)} failed.")

    # 5. Apply selective repair rules to failures
    repaired_docs = []
    not_repaired_docs = []

    for idx, doc, err in failed_first_pass:
        repaired_doc = dict(doc)
        repaired = False

        # Rule 1: Currency-formatted price
        price = repaired_doc.get('price')
        if isinstance(price, str):
            # Check if it looks like a currency-formatted string
            if any(c in price for c in ['$', '€', '£', '¥', ',']):
                cleaned = price
                for sym in ['$', '€', '£', '¥']:
                    cleaned = cleaned.replace(sym, '')
                cleaned = cleaned.replace(',', '')
                try:
                    repaired_doc['price'] = float(cleaned)
                    repaired = True
                    print(f"Repaired price for doc ID {repaired_doc['id']}: '{price}' -> {repaired_doc['price']}")
                except ValueError:
                    pass

        # Rule 2: Missing category
        if 'category' not in repaired_doc:
            repaired_doc['category'] = 'uncategorized'
            repaired = True
            print(f"Repaired missing category for doc ID {repaired_doc['id']}: set to 'uncategorized'")

        if repaired:
            repaired_docs.append((idx, repaired_doc))
        else:
            not_repaired_docs.append((idx, doc))

    # 6. Re-import only the repaired documents
    recovered_docs = []
    failed_docs = list(not_repaired_docs)  # start with failed docs that couldn't be repaired

    if repaired_docs:
        repaired_jsonl_bytes = '\n'.join(json.dumps(doc) for idx, doc in repaired_docs).encode('utf-8')
        response_second = requests.post(
            import_url,
            params=import_params,
            headers=import_headers,
            data=repaired_jsonl_bytes
        )

        if response_second.status_code != 200:
            print(f"Error: Second pass import returned status code {response_second.status_code}")
            print(response_second.text)
            return

        lines_second = response_second.text.strip().split('\n')

        for i, line in enumerate(lines_second):
            res = json.loads(line)
            idx, doc = repaired_docs[i]
            if res.get('success'):
                recovered_docs.append(doc)
            else:
                failed_docs.append((idx, doc))

    # 7. Compile report and IDs
    recovered_ids = sorted([doc['id'] for doc in recovered_docs])
    failed_ids = sorted([doc['id'] for idx, doc in failed_docs])

    report = {
        'total': total_docs,
        'imported_first_pass': len(imported_first_pass),
        'recovered': len(recovered_docs),
        'failed': len(failed_docs),
        'recovered_ids': recovered_ids,
        'failed_ids': failed_ids
    }

    report_path = '/home/user/import-pipeline/report.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print("\nIngestion Report compiled successfully:")
    print(json.dumps(report, indent=2))

    # 8. Sanity check collection count
    collection_info = client.collections[collection_name].retrieve()
    indexed_count = collection_info['num_documents']
    print(f"\nFinal document count in Typesense collection '{collection_name}': {indexed_count}")
    
    expected_indexed_count = len(imported_first_pass) + len(recovered_docs)
    if indexed_count == expected_indexed_count:
        print("Sanity check PASSED: Indexed count matches expectations.")
    else:
        print(f"Sanity check FAILED: Expected {expected_indexed_count}, but found {indexed_count}.")

if __name__ == '__main__':
    main()
