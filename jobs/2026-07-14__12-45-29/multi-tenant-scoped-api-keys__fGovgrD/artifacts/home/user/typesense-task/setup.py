#!/usr/bin/env python3
"""Multi-tenant search isolation via Typesense Scoped Search API Keys.

This script:
  1. Connects to a running Typesense server.
  2. Creates a `records` collection with the right schema.
  3. Bulk-indexes documents from /home/user/typesense-task/data/documents.jsonl.
  4. Creates a parent search-only API key scoped to documents:search on `records`.
  5. Derives a Scoped Search API Key for every distinct tenant.
  6. Verifies that each scoped key can only see its own tenant's docs
     and that the secret_notes field is excluded.
  7. Writes the artifact to /home/user/typesense-task/scoped_keys.json.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

import typesense

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
HOST = "localhost"
PORT = 8108
API_KEY = "xyz"  # bootstrap key passed to the server
COLLECTION = "records"
DATA_FILE = Path("/home/user/typesense-task/data/documents.jsonl")
ARTIFACT = Path("/home/user/typesense-task/scoped_keys.json")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def make_client(api_key: str) -> typesense.Client:
    return typesense.Client({
        "nodes": [{"host": HOST, "port": str(PORT), "protocol": "http"}],
        "api_key": api_key,
        "connection_timeout_seconds": 5,
    })


def load_documents(path: Path) -> list[dict]:
    docs = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


def discover_tenants(docs: list[dict]) -> list[str]:
    seen: "OrderedDict[str, None]" = OrderedDict()
    for d in docs:
        seen.setdefault(d["tenant_id"], None)
    return list(seen.keys())


# Independent HMAC-SHA256 derivation, mirrors typesense.keys.Keys.generate_scoped_search_key
def scoped_search_key(parent_key: str, parameters: dict) -> str:
    params_str = json.dumps(parameters)
    digest = base64.b64encode(
        hmac.new(parent_key.encode("utf-8"), params_str.encode("utf-8"),
                 digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    key_prefix = parent_key[0:4]
    raw = f"{digest}{key_prefix}{params_str}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


# -----------------------------------------------------------------------------
# 1. Connect & verify server
# -----------------------------------------------------------------------------
admin = make_client(API_KEY)
health = admin.operations.is_healthy()
print(f"[+] Server healthy: {health}")

# Make sure the collection does not pre-exist (clean slate from a previous run).
try:
    admin.collections[COLLECTION].delete()
    print(f"[i] Dropped existing collection '{COLLECTION}'")
except typesense.exceptions.ObjectNotFound:
    pass

# -----------------------------------------------------------------------------
# 2. Create collection
# -----------------------------------------------------------------------------
schema = {
    "name": COLLECTION,
    "enable_nested_fields": False,
    "fields": [
        {"name": "tenant_id", "type": "string", "facet": True},
        {"name": "title", "type": "string"},
        {"name": "category", "type": "string", "facet": True},
        {"name": "secret_notes", "type": "string", "index": False},
    ],
    "default_sorting_field": "",
}
admin.collections.create(schema)
print(f"[+] Created collection '{COLLECTION}'")

# -----------------------------------------------------------------------------
# 3. Index documents
# -----------------------------------------------------------------------------
docs = load_documents(DATA_FILE)
print(f"[+] Loaded {len(docs)} documents from {DATA_FILE}")
result = admin.collections[COLLECTION].documents.import_(
    docs, {"action": "upsert"}
)
print(f"[+] Import result (first 200 chars): {str(result)[:200]}")

# Wait until the documents are searchable
print("[+] Documents indexed.")

# -----------------------------------------------------------------------------
# 4. Create parent search-only API key
# -----------------------------------------------------------------------------
parent_key_schema = {
    "description": "Parent search-only key (parent for all tenant scoped keys)",
    "actions": ["documents:search"],
    "collections": [COLLECTION],
}
parent_resp = admin.keys.create(parent_key_schema)
parent_search_key = parent_resp["value"]
print(f"[+] Parent search-only key created (id={parent_resp['id']}, prefix={parent_search_key[:6]}...)")

# -----------------------------------------------------------------------------
# 5. Derive a Scoped Search API Key for every tenant
# -----------------------------------------------------------------------------
tenants = discover_tenants(docs)
print(f"[+] Discovered tenants: {tenants}")

scoped_keys: "OrderedDict[str, str]" = OrderedDict()
for tenant in tenants:
    embedded = {
        "filter_by": f"tenant_id:={tenant}",
        "exclude_fields": "secret_notes",
    }
    sk = scoped_search_key(parent_search_key, embedded)
    # Cross-check against the SDK implementation
    sdk_sk = admin.keys.generate_scoped_search_key(parent_search_key, embedded)
    if isinstance(sdk_sk, (bytes, bytearray)):
        sdk_sk = sdk_sk.decode("utf-8")
    assert sk == sdk_sk, f"SDK/HMAC mismatch for tenant {tenant}!"
    scoped_keys[tenant] = sk
    print(f"    • tenant={tenant} -> scoped key (prefix={sk[:6]}...)")

# -----------------------------------------------------------------------------
# 6. Verification: each scoped key sees only its own docs, secret_notes absent
# -----------------------------------------------------------------------------
print("\n[*] Verifying isolation ...")
failures = 0

# Build a quick lookup of expected (tenant_id, id) pairs
expected_ids = {d["tenant_id"]: d["id"] for d in docs}
all_ids_by_tenant: dict[str, set[str]] = {}
for d in docs:
    all_ids_by_tenant.setdefault(d["tenant_id"], set()).add(d["id"])

for tenant, sk in scoped_keys.items():
    scoped_client = make_client(sk)

    # 6a. Query without any extra filter -- should ONLY return own tenant's docs.
    res = scoped_client.collections[COLLECTION].documents.search({
        "q": "*",
        "query_by": "title",
        "per_page": 100,
    })
    hits = res.get("hits", [])
    seen_tenants = {h["document"]["tenant_id"] for h in hits}
    seen_ids = {h["document"]["id"] for h in hits}

    if seen_tenants != {tenant}:
        print(f"  [FAIL] tenant={tenant}: unexpected tenants in result: {seen_tenants}")
        failures += 1
    if seen_ids != all_ids_by_tenant[tenant]:
        print(f"  [FAIL] tenant={tenant}: wrong doc set, got {seen_ids}, "
              f"expected {all_ids_by_tenant[tenant]}")
        failures += 1
    if any("secret_notes" in h["document"] for h in hits):
        print(f"  [FAIL] tenant={tenant}: secret_notes field leaked")
        failures += 1
    else:
        print(f"  [OK]   tenant={tenant}: {len(hits)} hit(s), all own, no secret_notes")

    # 6b. Attempt to widen access: try filter_by=tenant_id:=<other_tenant>.
    # Because the embedded filter is AND-ed with the caller's filter, this
    # must produce zero hits (other_tenant:={other} AND tenant_id:={this}) -> empty.
    for other in tenants:
        if other == tenant:
            continue
        try:
            res2 = scoped_client.collections[COLLECTION].documents.search({
                "q": "*",
                "query_by": "title",
                "per_page": 100,
                "filter_by": f"tenant_id:={other}",
            })
        except typesense.exceptions.RequestUnauthorized as exc:
            # Filter-by overriding with a wider clause is rejected for scoped keys
            print(f"  [OK]   tenant={tenant}: cross-tenant filter_by={other!r} rejected ({exc})")
            continue
        except typesense.exceptions.RequestForbidden as exc:
            print(f"  [OK]   tenant={tenant}: cross-tenant filter_by={other!r} forbidden ({exc})")
            continue
        hits2 = res2.get("hits", [])
        # Must be empty: a tenant cannot see another tenant's documents
        if hits2:
            print(f"  [FAIL] tenant={tenant}: cross-tenant filter_by={other!r} returned {len(hits2)} hits")
            failures += 1
        else:
            print(f"  [OK]   tenant={tenant}: cross-tenant filter_by={other!r} returned 0 hits")

    # 6c. Attempt to override exclude_fields -> must not surface secret_notes.
    try:
        res3 = scoped_client.collections[COLLECTION].documents.search({
            "q": "*",
            "query_by": "title",
            "per_page": 100,
            "exclude_fields": "",  # try to include everything
        })
        for h in res3.get("hits", []):
            if "secret_notes" in h["document"]:
                print(f"  [FAIL] tenant={tenant}: secret_notes leaked via override")
                failures += 1
                break
        else:
            print(f"  [OK]   tenant={tenant}: exclude_fields override did not leak secret_notes")
    except typesense.exceptions.RequestUnauthorized:
        print(f"  [OK]   tenant={tenant}: exclude_fields override rejected")

# 6d. The parent key must NOT be usable for indexing/deleting.
try:
    parent_client = make_client(parent_search_key)
    parent_client.collections[COLLECTION].documents.create(
        {"id": "x", "tenant_id": "evil", "title": "x", "category": "x", "secret_notes": "x"}
    )
    print("  [FAIL] parent key allowed document creation!")
    failures += 1
except (typesense.exceptions.RequestForbidden,
        typesense.exceptions.RequestUnauthorized) as exc:
    print(f"  [OK]   parent key cannot create documents ({type(exc).__name__}: {exc})")

# -----------------------------------------------------------------------------
# 7. Write artifact
# -----------------------------------------------------------------------------
artifact = {
    "collection": COLLECTION,
    "parent_search_key": parent_search_key,
    "scoped_keys": scoped_keys,
}
ARTIFACT.write_text(json.dumps(artifact, indent=2))
print(f"\n[+] Wrote artifact to {ARTIFACT}")

if failures:
    print(f"\n[!] {failures} verification failure(s)")
    sys.exit(1)
print("\n[+] All verifications passed.")
