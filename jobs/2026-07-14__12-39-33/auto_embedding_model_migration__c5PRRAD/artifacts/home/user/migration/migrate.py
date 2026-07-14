#!/usr/bin/env python3
"""
Migrate the 'notes' collection's content_embedding field
from 4-dimensional to 8-dimensional vectors in-place.

Revised strategy – Typesense stores raw field data in documents even after a
field is dropped from the schema.  When we later try to add a new vector field
with a different num_dim, it re-validates all stored documents and rejects any
whose stored value has the wrong number of dimensions.

Correct order of operations
───────────────────────────
1. Drop   content_embedding from the schema.
2. Upsert every document with  content_embedding = <null>  (action=update)
   using the "auto" schema so the null goes through without type checking.
   Actually Typesense won't accept null for a missing field either — instead
   we upsert with ONLY the non-embedding fields so the stored embedding key is
   removed from each document record.
   The cleanest way: export every doc, strip the embedding, re-import with
   action=upsert so the full document (minus the field) is stored cleanly.
3. Add    content_embedding back with num_dim=8, optional=True.
4. Upsert every document with its new 8-dim embedding (action=update).
5. Make   content_embedding non-optional (drop + re-add without optional).
6. Verify schema and run a vector-search smoke test.
"""

import json
import sys
import urllib.request
import urllib.error
import io

BASE_URL   = "http://localhost:8108"
API_KEY    = "xyz"
COLLECTION = "notes"
VECTORS_FILE = "/home/user/migration/new_vectors.jsonl"
HEADERS    = {"X-TYPESENSE-API-KEY": API_KEY, "Content-Type": "application/json"}


# ── helpers ──────────────────────────────────────────────────────────────────

def api(method: str, path: str, body=None) -> dict:
    url  = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()
        print(f"  HTTP {e.code} {method} {path}: {msg}", file=sys.stderr)
        raise


def bulk_import_ndjson(lines: list[str], action: str) -> list[dict]:
    """POST newline-delimited JSON strings to the import endpoint."""
    url     = f"{BASE_URL}/collections/{COLLECTION}/documents/import?action={action}"
    payload = "\n".join(lines).encode()
    headers = {**HEADERS, "Content-Type": "text/plain"}
    req     = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode().strip().split("\n")
    return [json.loads(l) for l in raw]


def bulk_import_file(filepath: str, action: str) -> list[dict]:
    """POST a .jsonl file to the import endpoint."""
    url = f"{BASE_URL}/collections/{COLLECTION}/documents/import?action={action}"
    with open(filepath, "rb") as fh:
        data = fh.read()
    headers = {**HEADERS, "Content-Type": "text/plain"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode().strip().split("\n")
    return [json.loads(l) for l in raw]


def export_all_documents() -> list[dict]:
    """Export every document in the collection via the export endpoint."""
    url = f"{BASE_URL}/collections/{COLLECTION}/documents/export"
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode().strip().split("\n")
    return [json.loads(l) for l in raw if l.strip()]


def assert_ok(results: list[dict], label: str):
    failures = [r for r in results if not r.get("success")]
    if failures:
        print(f"  FAILURES in {label}: {failures}", file=sys.stderr)
        sys.exit(1)
    print(f"  {label}: {len(results)} documents OK")


def field_schema(schema: dict, name: str) -> dict | None:
    return next((f for f in schema["fields"] if f["name"] == name), None)


def add_embedding_field(optional: bool):
    result = api("PATCH", f"/collections/{COLLECTION}", {"fields": [{
        "name":    "content_embedding",
        "type":    "float[]",
        "num_dim": 8,
        "optional": optional,
    }]})
    print(f"  Added content_embedding (optional={optional}): {result}")


def drop_embedding_field():
    result = api("PATCH", f"/collections/{COLLECTION}", {"fields": [
        {"name": "content_embedding", "drop": True}
    ]})
    print(f"  Dropped content_embedding: {result}")


# ── Step 0: sanity check ──────────────────────────────────────────────────────

print("=== Step 0: Sanity check ===")
health = api("GET", "/health")
assert health.get("ok"), f"Server not healthy: {health}"
print(f"  Server: {health}")

schema = api("GET", f"/collections/{COLLECTION}")
print(f"  Collection '{COLLECTION}': {schema['num_documents']} documents")

emb_field = field_schema(schema, "content_embedding")
if emb_field:
    print(f"  content_embedding: num_dim={emb_field.get('num_dim')}, in schema=True")
else:
    print("  content_embedding: NOT in schema (was already dropped earlier)")

# ── Step 1: Drop the field if it is still in the schema ──────────────────────

print("\n=== Step 1: Drop content_embedding from schema ===")
schema = api("GET", f"/collections/{COLLECTION}")
if field_schema(schema, "content_embedding"):
    drop_embedding_field()
else:
    print("  Already dropped – skipping")

schema = api("GET", f"/collections/{COLLECTION}")
assert field_schema(schema, "content_embedding") is None, "Drop did not take effect"
print("  Confirmed: content_embedding absent from schema")

# ── Step 2: Export all docs, strip the embedding, re-upsert ──────────────────
# This removes the stale 4-dim raw data from each stored document record.

print("\n=== Step 2: Strip old embedding data from stored documents ===")
docs = export_all_documents()
print(f"  Exported {len(docs)} documents")

stripped_lines = []
for doc in docs:
    doc.pop("content_embedding", None)   # remove old 4-dim data if present
    stripped_lines.append(json.dumps(doc))

results = bulk_import_ndjson(stripped_lines, action="upsert")
assert_ok(results, "strip-upsert")

# Confirm the stored doc no longer carries the old embedding
doc1 = api("GET", f"/collections/{COLLECTION}/documents/1")
assert "content_embedding" not in doc1, \
    f"Old embedding still present in doc 1 after strip: {doc1}"
print(f"  Doc 1 keys after strip: {list(doc1.keys())} ✓")

# ── Step 3: Add content_embedding with num_dim=8, optional=True ──────────────

print("\n=== Step 3: Add content_embedding (num_dim=8, optional=True) ===")
add_embedding_field(optional=True)

schema = api("GET", f"/collections/{COLLECTION}")
f = field_schema(schema, "content_embedding")
assert f is not None and f["num_dim"] == 8, f"Unexpected field state: {f}"
print(f"  Confirmed: num_dim={f['num_dim']}, optional={f['optional']} ✓")

# ── Step 4: Upsert 8-dim embeddings ──────────────────────────────────────────

print("\n=== Step 4: Upsert new 8-dimensional embeddings ===")
results = bulk_import_file(VECTORS_FILE, action="update")
assert_ok(results, "embedding-upsert")

# ── Step 5: Make the field non-optional ──────────────────────────────────────

print("\n=== Step 5: Make content_embedding non-optional ===")
drop_embedding_field()

schema = api("GET", f"/collections/{COLLECTION}")
assert field_schema(schema, "content_embedding") is None, "Drop did not take effect"

add_embedding_field(optional=False)

schema = api("GET", f"/collections/{COLLECTION}")
f = field_schema(schema, "content_embedding")
assert f is not None and not f["optional"] and f["num_dim"] == 8, \
    f"Unexpected field state: {f}"
print(f"  Confirmed: num_dim={f['num_dim']}, optional={f['optional']} ✓")

# ── Step 6: Final verification ────────────────────────────────────────────────

print("\n=== Step 6: Final verification ===")
schema = api("GET", f"/collections/{COLLECTION}")
print(f"  Total documents: {schema['num_documents']}")
f = field_schema(schema, "content_embedding")
assert f["num_dim"] == 8,      f"num_dim={f['num_dim']} expected 8"
assert f["type"] == "float[]", f"type={f['type']} expected float[]"
assert not f["optional"],      "field should be non-optional"
print(f"  content_embedding: type={f['type']}, num_dim={f['num_dim']}, "
      f"optional={f['optional']} ✓")

# Check every document has the right embedding length and unchanged fields
docs = export_all_documents()
print(f"  Checking {len(docs)} documents …")

# Build expected embeddings from the jsonl file
expected: dict[str, list] = {}
with open(VECTORS_FILE) as fh:
    for line in fh:
        obj = json.loads(line)
        expected[obj["id"]] = obj["content_embedding"]

for doc in docs:
    doc_id = doc["id"]
    emb    = doc.get("content_embedding", [])
    assert len(emb) == 8, f"Doc {doc_id}: embedding has {len(emb)} dims"
    if doc_id in expected:
        assert emb == expected[doc_id], \
            f"Doc {doc_id}: embedding mismatch\n  got:      {emb}\n  expected: {expected[doc_id]}"
    # Verify non-embedding fields are intact
    for field in ("title", "content", "category"):
        assert field in doc, f"Doc {doc_id} is missing field '{field}'"
print("  All documents verified ✓")

# ── Step 7: Vector-search smoke test ─────────────────────────────────────────

print("\n=== Step 7: Vector search smoke test ===")
# Query vector matches doc 1's new embedding exactly → should be the top hit
query_vec = ",".join(str(v) for v in [0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18])
import urllib.parse
vq = urllib.parse.quote(f"content_embedding:([{query_vec}],k:3)")
search_result = api("GET",
    f"/collections/{COLLECTION}/documents/search"
    f"?q=*&query_by=title&vector_query={vq}&per_page=3")

hits = search_result.get("hits", [])
assert hits, "Vector search returned no hits"
print(f"  Got {len(hits)} hit(s):")
for h in hits:
    d = h["document"]
    print(f"    id={d['id']}, title='{d['title']}', "
          f"embedding_dims={len(d.get('content_embedding', []))}")

top_id = hits[0]["document"]["id"]
assert top_id == "1", f"Expected doc id=1 as top hit (exact match), got id={top_id}"
print(f"  Top hit is doc id=1 (exact-match vector) ✓")

print("\n✅  Migration completed successfully.")
