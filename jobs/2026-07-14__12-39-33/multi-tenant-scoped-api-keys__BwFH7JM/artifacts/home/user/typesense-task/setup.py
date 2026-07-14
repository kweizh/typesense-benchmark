#!/usr/bin/env python3
"""
Multi-tenant Typesense setup with scoped search API key isolation.

Steps:
  1. Create the 'records' collection.
  2. Import all documents from documents.jsonl.
  3. Create a parent search-only API key (documents:search / records).
  4. Derive one Scoped Search API Key per tenant (embeds filter_by + exclude_fields).
  5. Verify isolation: each scoped key returns only its own tenant's docs.
  6. Write /home/user/typesense-task/scoped_keys.json.
"""

import json
import sys
import time

import typesense

# ---------------------------------------------------------------------------
# Client (bootstrap admin key)
# ---------------------------------------------------------------------------
BOOTSTRAP_KEY = "xyz"
HOST = "localhost"
PORT = 8108
DATA_PATH = "/home/user/typesense-task/data/documents.jsonl"
ARTIFACT_PATH = "/home/user/typesense-task/scoped_keys.json"
COLLECTION_NAME = "records"

client = typesense.Client(
    {
        "nodes": [{"host": HOST, "port": str(PORT), "protocol": "http"}],
        "api_key": BOOTSTRAP_KEY,
        "connection_timeout_seconds": 10,
    }
)

# ---------------------------------------------------------------------------
# 1. Create collection
# ---------------------------------------------------------------------------
print("==> Creating collection …")

# Drop if already exists (idempotent re-runs)
try:
    client.collections[COLLECTION_NAME].delete()
    print("    (dropped existing collection)")
except Exception:
    pass

schema = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "id",           "type": "string"},
        {"name": "tenant_id",    "type": "string", "facet": True},
        {"name": "title",        "type": "string"},
        {"name": "category",     "type": "string", "facet": True},
        {"name": "secret_notes", "type": "string", "index": False, "optional": True},
    ],
    "default_sorting_field": "",
}

collection = client.collections.create(schema)
print(f"    Collection '{collection['name']}' created with {len(collection['fields'])} fields.")

# ---------------------------------------------------------------------------
# 2. Import documents
# ---------------------------------------------------------------------------
print("==> Importing documents …")

with open(DATA_PATH) as fh:
    lines = [line.strip() for line in fh if line.strip()]

documents = [json.loads(line) for line in lines]

# Discover distinct tenants while we're here
tenants = sorted({doc["tenant_id"] for doc in documents})
print(f"    Found {len(documents)} documents across {len(tenants)} tenants: {tenants}")

response = client.collections[COLLECTION_NAME].documents.import_(
    documents, {"action": "upsert"}
)

# import_ returns a list of per-document result dicts
failures = [r for r in response if not r.get("success", False)]
if failures:
    print(f"    ERROR: {len(failures)} document(s) failed to import:")
    for f in failures:
        print(f"      {f}")
    sys.exit(1)

print(f"    All {len(documents)} documents imported successfully.")

# Give the index a moment to flush
time.sleep(1)

# ---------------------------------------------------------------------------
# 3. Create parent search-only API key
# ---------------------------------------------------------------------------
print("==> Creating parent search-only API key …")

# Delete any old key with the same description so this script is idempotent
existing_keys = client.keys.retrieve()
for k in existing_keys.get("keys", []):
    if k.get("description") == "parent-search-key":
        client.keys[k["id"]].delete()
        print(f"    (deleted old parent key id={k['id']})")

parent_key_obj = client.keys.create(
    {
        "description": "parent-search-key",
        "actions": ["documents:search"],
        "collections": [COLLECTION_NAME],
    }
)

parent_key_value = parent_key_obj["value"]
parent_key_id    = parent_key_obj["id"]
print(f"    Parent key created  id={parent_key_id}  value={parent_key_value!r}")

# ---------------------------------------------------------------------------
# 4. Generate Scoped Search API Keys — one per tenant
# ---------------------------------------------------------------------------
print("==> Generating scoped search API keys …")

# Build a temporary client that uses the parent key, needed by generate_scoped_search_key
parent_client = typesense.Client(
    {
        "nodes": [{"host": HOST, "port": str(PORT), "protocol": "http"}],
        "api_key": parent_key_value,
        "connection_timeout_seconds": 10,
    }
)

scoped_keys: dict[str, str] = {}

for tenant_id in tenants:
    embedded_params = {
        "filter_by":      f"tenant_id:={tenant_id}",
        "exclude_fields": "secret_notes",
    }
    scoped_key = parent_client.keys.generate_scoped_search_key(
        parent_key_value,
        embedded_params,
    )
    # SDK returns bytes; decode to a plain str for JSON serialisation
    if isinstance(scoped_key, bytes):
        scoped_key = scoped_key.decode("utf-8")
    scoped_keys[tenant_id] = scoped_key
    print(f"    {tenant_id:12s}  →  {scoped_key[:40]}…")

# ---------------------------------------------------------------------------
# 5. Verify isolation
# ---------------------------------------------------------------------------
print("==> Verifying tenant isolation …")

def search_with_key(api_key: str, query: str = "*", extra_filter: str = "") -> list[dict]:
    """Return the list of hit documents for a wildcard search using the given key."""
    params = {
        "q":            query,
        "query_by":     "title",
        "per_page":     250,
    }
    if extra_filter:
        params["filter_by"] = extra_filter

    sc = typesense.Client(
        {
            "nodes": [{"host": HOST, "port": str(PORT), "protocol": "http"}],
            "api_key": api_key,
            "connection_timeout_seconds": 10,
        }
    )
    result = sc.collections[COLLECTION_NAME].documents.search(params)
    return [hit["document"] for hit in result["hits"]]


all_passed = True

for tenant_id, scoped_key in scoped_keys.items():
    # --- a) Basic wildcard search must return only this tenant's docs ----------
    hits = search_with_key(scoped_key)
    returned_tenants = {d["tenant_id"] for d in hits}
    expected_ids     = {d["id"] for d in documents if d["tenant_id"] == tenant_id}
    returned_ids     = {d["id"] for d in hits}

    ok_isolation = returned_tenants == {tenant_id}
    ok_completeness = returned_ids == expected_ids

    # --- b) Caller tries to widen filter (should still be confined) -----------
    try:
        cross_hits = search_with_key(scoped_key, extra_filter="tenant_id:!=__none__")
        cross_tenants = {d["tenant_id"] for d in cross_hits}
        ok_tamper = cross_tenants <= {tenant_id}
    except Exception as exc:
        # Typesense may reject the request — that also counts as safe.
        ok_tamper = True
        cross_tenants = set()

    # --- c) secret_notes must not appear in any hit ---------------------------
    ok_secret = all("secret_notes" not in d for d in hits)

    status = "PASS" if (ok_isolation and ok_completeness and ok_tamper and ok_secret) else "FAIL"
    if status == "FAIL":
        all_passed = False

    print(
        f"    [{status}] {tenant_id:12s}  "
        f"isolation={ok_isolation}  completeness={ok_completeness}  "
        f"tamper_proof={ok_tamper}  secret_hidden={ok_secret}"
    )
    if not ok_isolation:
        print(f"           returned tenants: {returned_tenants}")
    if not ok_completeness:
        print(f"           expected ids: {expected_ids}  returned ids: {returned_ids}")
    if not ok_tamper:
        print(f"           tampered query returned tenants: {cross_tenants}")
    if not ok_secret:
        bad = [d for d in hits if "secret_notes" in d]
        print(f"           docs exposing secret_notes: {[d['id'] for d in bad]}")

if not all_passed:
    print("\nERROR: One or more isolation checks FAILED.")
    sys.exit(1)

print("\nAll isolation checks passed ✓")

# ---------------------------------------------------------------------------
# 6. Write artifact
# ---------------------------------------------------------------------------
print("==> Writing artifact …")

artifact = {
    "collection":         COLLECTION_NAME,
    "parent_search_key":  parent_key_value,
    "scoped_keys":        scoped_keys,
}

with open(ARTIFACT_PATH, "w") as fh:
    json.dump(artifact, fh, indent=2)

print(f"    Written to {ARTIFACT_PATH}")
print("\nDone.")
