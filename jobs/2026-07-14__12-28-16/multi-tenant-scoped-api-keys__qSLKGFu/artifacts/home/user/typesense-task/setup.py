#!/usr/bin/env python3
"""
Multi-Tenant Search Isolation with Typesense Scoped Search API Keys.

This script:
  1. Creates the `records` collection (tenant_id filterable/faceted, title full-text).
  2. Indexes every document from data/documents.jsonl.
  3. Creates a parent search-only API key (documents:search on `records` only).
  4. Derives a scoped search API key per tenant embedding filter_by + exclude_fields.
  5. Verifies strict tenant isolation (including tamper attempts).
  6. Writes the artifact scoped_keys.json.
"""

import json
import time
import sys

import requests
import typesense

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = 8108
TYPESENSE_PROTOCOL = "http"
BOOTSTRAP_API_KEY = "xyz"            # admin / bootstrap key
COLLECTION_NAME = "records"
DATA_FILE = "/home/user/typesense-task/data/documents.jsonl"
ARTIFACT_FILE = "/home/user/typesense-task/scoped_keys.json"

BASE_URL = f"{TYPESENSE_PROTOCOL}://{TYPESENSE_HOST}:{TYPESENSE_PORT}"


def wait_for_server():
    """Wait until the Typesense server responds to /health."""
    for _ in range(60):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200 and r.json().get("ok"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Typesense server did not become healthy in time")


def get_admin_client():
    return typesense.Client(
        {
            "nodes": [
                {
                    "host": TYPESENSE_HOST,
                    "port": TYPESENSE_PORT,
                    "protocol": TYPESENSE_PROTOCOL,
                }
            ],
            "api_key": BOOTSTRAP_API_KEY,
            "connection_timeout_seconds": 10,
        }
    )


def load_documents():
    """Load all documents from the JSONL file and discover distinct tenants."""
    docs = []
    tenants = set()
    with open(DATA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            docs.append(doc)
            tenants.add(doc["tenant_id"])
    return docs, sorted(tenants)


def create_collection(client):
    """Create the `records` collection (delete first if it already exists)."""
    try:
        client.collections[COLLECTION_NAME].delete()
        print(f"Deleted pre-existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass

    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "id", "type": "string", "facet": False},
            {"name": "tenant_id", "type": "string", "facet": True},
            {"name": "title", "type": "string"},
            {"name": "category", "type": "string", "facet": True},
            {"name": "secret_notes", "type": "string"},
        ],
    }
    result = client.collections.create(schema)
    print(f"Created collection: {result['name']}")
    return result


def index_documents(client, docs):
    """Index every document into the records collection."""
    # Use the documents.import_ method with JSONL format
    jsonl_lines = "\n".join(json.dumps(d) for d in docs) + "\n"
    res = client.collections[COLLECTION_NAME].documents.import_(jsonl_lines.encode("utf-8"))
    # `import_` returns a JSONL string (one JSON object per line per document)
    if isinstance(res, bytes):
        res = res.decode("utf-8")
    num_success = 0
    num_fail = 0
    failures = []
    for line in res.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if item.get("success"):
            num_success += 1
        else:
            num_fail += 1
            failures.append(item)
    print(f"Indexed {num_success} documents successfully, {num_fail} failures")
    if num_fail:
        raise RuntimeError(f"Failed to index {num_fail} documents: {failures}")
    return num_success


def create_parent_search_key(client):
    """Create a parent search-only API key restricted to documents:search on `records`."""
    key_schema = {
        "description": "Parent search-only key for records collection (multi-tenant scoped keys derived from this)",
        "actions": ["documents:search"],
        "collections": [COLLECTION_NAME],
    }
    result = client.keys.create(key_schema)
    parent_key = result["value"]
    print(f"Created parent search-only API key (id={result.get('id')}): {parent_key[:12]}...")
    return parent_key


def generate_scoped_keys(parent_key, tenants):
    """Generate a scoped search API key for each tenant."""
    client = get_admin_client()
    scoped_keys = {}
    for tenant in tenants:
        parameters = {
            "filter_by": f"tenant_id:={tenant}",
            "exclude_fields": "secret_notes",
        }
        scoped_key = client.keys.generate_scoped_search_key(parent_key, parameters)
        # SDK returns bytes; decode to str
        if isinstance(scoped_key, bytes):
            scoped_key = scoped_key.decode("utf-8")
        scoped_keys[tenant] = scoped_key
        print(f"Generated scoped key for tenant '{tenant}': {scoped_key[:24]}...")
    return scoped_keys


def search_with_scoped_key(scoped_key, query="*", filter_by=None, per_page=250):
    """Perform a search using a scoped key via the REST API directly."""
    params = {
        "q": query,
        "query_by": "title",
        "per_page": per_page,
    }
    if filter_by:
        params["filter_by"] = filter_by
    r = requests.get(
        f"{BASE_URL}/collections/{COLLECTION_NAME}/documents/search",
        headers={"X-TYPESENSE-API-KEY": scoped_key},
        params=params,
        timeout=10,
    )
    return r


def verify_isolation(tenants, scoped_keys, docs):
    """Verify each scoped key returns only its tenant's docs and cannot be tricked."""
    tenant_doc_ids = {}
    for doc in docs:
        tenant_doc_ids.setdefault(doc["tenant_id"], set()).add(doc["id"])

    all_ok = True

    for tenant in tenants:
        key = scoped_keys[tenant]
        expected_ids = tenant_doc_ids[tenant]

        # --- Test 1: normal search returns only this tenant's documents ---
        r = search_with_scoped_key(key)
        if r.status_code != 200:
            print(f"  [FAIL] tenant={tenant}: normal search returned HTTP {r.status_code}: {r.text}")
            all_ok = False
            continue
        hits = r.json().get("hits", [])
        returned_ids = {h["document"]["id"] for h in hits}
        if returned_ids != expected_ids:
            print(f"  [FAIL] tenant={tenant}: expected ids {expected_ids}, got {returned_ids}")
            all_ok = False
        else:
            print(f"  [PASS] tenant={tenant}: normal search returned exactly {len(returned_ids)} own documents")

        # --- Test 2: secret_notes must never appear in responses ---
        for h in hits:
            doc = h["document"]
            if "secret_notes" in doc:
                print(f"  [FAIL] tenant={tenant}: secret_notes leaked for doc {doc['id']}: {doc['secret_notes']}")
                all_ok = False
                break
        else:
            print(f"  [PASS] tenant={tenant}: secret_notes excluded from all results")

        # --- Test 3: tamper attempt — try to override filter_by to another tenant ---
        other_tenant = next(t for t in tenants if t != tenant)
        r = search_with_scoped_key(key, filter_by=f"tenant_id:={other_tenant}")
        if r.status_code != 200:
            # Even an error is acceptable as long as we don't get other tenant's data
            print(f"  [PASS] tenant={tenant}: tampered filter_by rejected (HTTP {r.status_code})")
        else:
            hits = r.json().get("hits", [])
            returned_ids = {h["document"]["id"] for h in hits}
            other_ids = tenant_doc_ids[other_tenant]
            leaked = returned_ids & other_ids
            if leaked:
                print(f"  [FAIL] tenant={tenant}: tampered filter_by leaked other tenant docs: {leaked}")
                all_ok = False
            elif returned_ids == expected_ids:
                print(f"  [PASS] tenant={tenant}: tampered filter_by ignored, still only own docs returned")
            else:
                print(f"  [PASS] tenant={tenant}: tampered filter_by did not leak other tenant docs (got {returned_ids})")

        # --- Test 4: tamper attempt — try to include secret_notes via include_fields ---
        r = requests.get(
            f"{BASE_URL}/collections/{COLLECTION_NAME}/documents/search",
            headers={"X-TYPESENSE-API-KEY": key},
            params={"q": "*", "query_by": "title", "include_fields": "secret_notes"},
            timeout=10,
        )
        if r.status_code == 200:
            hits = r.json().get("hits", [])
            leaked_secret = any("secret_notes" in h["document"] for h in hits)
            if leaked_secret:
                print(f"  [FAIL] tenant={tenant}: include_fields override leaked secret_notes")
                all_ok = False
            else:
                print(f"  [PASS] tenant={tenant}: include_fields override could not leak secret_notes")
        else:
            print(f"  [PASS] tenant={tenant}: include_fields override rejected (HTTP {r.status_code})")

    if not all_ok:
        raise RuntimeError("Isolation verification FAILED — see output above")
    print("\n✅ All isolation checks passed!")


def main():
    print("=" * 70)
    print("Typesense Multi-Tenant Scoped Search Key Setup")
    print("=" * 70)

    wait_for_server()
    print("Typesense server is healthy.\n")

    client = get_admin_client()

    # Step 1: Create collection
    print("--- Step 1: Create collection ---")
    create_collection(client)

    # Step 2: Load & index documents
    print("\n--- Step 2: Load & index documents ---")
    docs, tenants = load_documents()
    print(f"Loaded {len(docs)} documents with {len(tenants)} tenants: {tenants}")
    index_documents(client, docs)

    # Step 3: Create parent search-only key
    print("\n--- Step 3: Create parent search-only API key ---")
    parent_key = create_parent_search_key(client)

    # Step 4: Generate scoped keys per tenant
    print("\n--- Step 4: Generate scoped search API keys ---")
    scoped_keys = generate_scoped_keys(parent_key, tenants)

    # Step 5: Verify isolation
    print("\n--- Step 5: Verify tenant isolation ---")
    verify_isolation(tenants, scoped_keys, docs)

    # Step 6: Write artifact
    print("\n--- Step 6: Write artifact file ---")
    artifact = {
        "collection": COLLECTION_NAME,
        "parent_search_key": parent_key,
        "scoped_keys": {t: scoped_keys[t] for t in tenants},
    }
    with open(ARTIFACT_FILE, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"Wrote artifact to {ARTIFACT_FILE}")
    print(json.dumps(artifact, indent=2))

    print("\n" + "=" * 70)
    print("Setup complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()