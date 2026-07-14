import json
import typesense
import sys

def main():
    # 1. Initialize admin client
    client = typesense.Client({
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'api_key': 'xyz',
        'connection_timeout_seconds': 5
    })

    # 2. Recreate collection if exists
    collection_name = 'records'
    try:
        client.collections[collection_name].delete()
        print(f"Deleted existing collection '{collection_name}'")
    except Exception as e:
        print(f"Collection '{collection_name}' did not exist or could not be deleted: {e}")

    # 3. Create collection
    schema = {
        'name': collection_name,
        'fields': [
            {'name': 'tenant_id', 'type': 'string', 'facet': True},
            {'name': 'title', 'type': 'string'},
            {'name': 'category', 'type': 'string', 'facet': True, 'optional': True},
            {'name': 'secret_notes', 'type': 'string', 'optional': True}
        ]
    }
    client.collections.create(schema)
    print(f"Created collection '{collection_name}' successfully")

    # 4. Read documents
    documents_path = '/home/user/typesense-task/data/documents.jsonl'
    documents = []
    tenants = set()
    with open(documents_path, 'r') as f:
        for line in f:
            if line.strip():
                doc = json.loads(line)
                documents.append(doc)
                if 'tenant_id' in doc:
                    tenants.add(doc['tenant_id'])

    print(f"Read {len(documents)} documents. Found tenants: {sorted(list(tenants))}")

    # 5. Index documents
    import_results = client.collections[collection_name].documents.import_(documents, {'action': 'upsert'})
    print("Import results:")
    for res in import_results:
        print(res)

    # 6. Create parent search-only API key
    # Limited to documents:search on 'records' collection
    parent_key_schema = {
        'description': 'Parent search-only key for multi-tenant isolation',
        'actions': ['documents:search'],
        'collections': [collection_name]
    }
    parent_key_resp = client.keys.create(parent_key_schema)
    parent_key = parent_key_resp['value']
    print(f"Created parent search-only key: {parent_key}")

    # 7. Generate Scoped Search API Key for each tenant
    scoped_keys = {}
    for tenant_id in sorted(list(tenants)):
        # Parameters to embed in the scoped search key
        parameters = {
            'filter_by': f'tenant_id:={tenant_id}',
            'exclude_fields': 'secret_notes'
        }
        # Generate the scoped key
        scoped_key = client.keys.generate_scoped_search_key(parent_key, parameters).decode('utf-8')
        scoped_keys[tenant_id] = scoped_key
        print(f"Generated scoped key for tenant '{tenant_id}': {scoped_key}")

    # 8. Verify scoped keys
    print("\n--- Starting Verification ---")
    verification_passed = True
    for tenant_id, scoped_key in scoped_keys.items():
        print(f"\nVerifying tenant: {tenant_id}")
        tenant_client = typesense.Client({
            'nodes': [{
                'host': 'localhost',
                'port': '8108',
                'protocol': 'http'
            }],
            'api_key': scoped_key,
            'connection_timeout_seconds': 5
        })

        # Test A: Basic search should return ONLY this tenant's documents
        search_params = {
            'q': '*',
            'query_by': 'title'
        }
        try:
            results = tenant_client.collections[collection_name].documents.search(search_params)
            hits = results.get('hits', [])
            print(f"  Test A (basic search): retrieved {len(hits)} documents")
            
            # Check that every document returned belongs to this tenant and doesn't contain secret_notes
            for hit in hits:
                doc = hit['document']
                doc_tenant = doc.get('tenant_id')
                if doc_tenant != tenant_id:
                    print(f"  [FAIL] Document {doc.get('id')} belongs to tenant '{doc_tenant}', expected '{tenant_id}'")
                    verification_passed = False
                if 'secret_notes' in doc:
                    print(f"  [FAIL] Document {doc.get('id')} contains 'secret_notes' field!")
                    verification_passed = False
        except Exception as e:
            print(f"  [FAIL] Basic search failed: {e}")
            verification_passed = False

        # Test B: Attempt to filter for another tenant
        # Since the scoped key embeds 'filter_by': 'tenant_id:=<tenant_id>', Typesense should AND this with any user-supplied filter.
        # So filter_by: 'tenant_id:=other_tenant' should result in tenant_id:=<tenant_id> AND tenant_id:=other_tenant, which returns 0 results.
        other_tenant = [t for t in tenants if t != tenant_id][0]
        search_params_tampered = {
            'q': '*',
            'query_by': 'title',
            'filter_by': f'tenant_id:={other_tenant}'
        }
        try:
            results_tampered = tenant_client.collections[collection_name].documents.search(search_params_tampered)
            hits_tampered = results_tampered.get('hits', [])
            print(f"  Test B (tampered filter for '{other_tenant}'): retrieved {len(hits_tampered)} documents")
            if len(hits_tampered) > 0:
                print(f"  [FAIL] Tampered search returned documents! Hits: {hits_tampered}")
                verification_passed = False
            else:
                print("  [PASS] Tampered search returned 0 documents as expected.")
        except Exception as e:
            print(f"  [FAIL] Tampered search failed: {e}")
            verification_passed = False

    if verification_passed:
        print("\nAll verifications PASSED!")
    else:
        print("\nSome verifications FAILED!")
        sys.exit(1)

    # 9. Write results to artifact file
    output_path = '/home/user/typesense-task/scoped_keys.json'
    result_data = {
        'collection': collection_name,
        'parent_search_key': parent_key,
        'scoped_keys': scoped_keys
    }
    with open(output_path, 'w') as f:
        json.dump(result_data, f, indent=2)
    print(f"\nResults written to {output_path}")

if __name__ == '__main__':
    main()
