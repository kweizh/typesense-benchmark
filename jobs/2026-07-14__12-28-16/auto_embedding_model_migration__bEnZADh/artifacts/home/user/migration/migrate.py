#!/usr/bin/env python3
"""
Migrate the 'notes' collection's content_embedding field from 4-dim to 8-dim
in place, without dropping/recreating the collection.

Strategy:
  1. Drop the old content_embedding (num_dim=4) from the schema.
  2. Full-replace every document (PUT) WITHOUT content_embedding, so the stale
     4-dim vector data is cleared from the on-disk document store.
  3. Re-add content_embedding with num_dim=8 (optional, so docs with no
     vector yet pass validation).
  4. Update every document with its new 8-dim content_embedding.
  5. (Optional) Tighten content_embedding to non-optional.

If step 3 fails because stale data persists, fall back to a temporary-field
strategy:
  a. Re-add content_embedding with num_dim=4.
  b. Add a temp field content_embedding_v2 with num_dim=8 (optional).
  c. Update all docs to populate content_embedding_v2.
  d. Drop content_embedding (4-dim).
  e. Full-replace all docs without content_embedding (clear stale data).
  f. Add content_embedding with num_dim=8 (optional).
  g. Update all docs to populate content_embedding.
  h. Drop content_embedding_v2.
"""

import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION = "notes"
HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}


def ts_request(method, path, body=None):
    """Send a request to Typesense and return the parsed JSON response."""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  ERROR {e.code}: {err_body}", file=sys.stderr)
        try:
            return json.loads(err_body)
        except Exception:
            return {"message": err_body}


def load_new_vectors(path):
    """Load the pre-generated 8-dim vectors from the JSONL file."""
    vectors = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            vectors[obj["id"]] = obj["content_embedding"]
    return vectors


def fetch_all_documents():
    """Fetch all documents from the collection (paginated)."""
    docs = []
    page = 1
    while True:
        resp = ts_request(
            "GET",
            f"/collections/{COLLECTION}/documents/search?q=*&query_by=title&per_page=250&page={page}",
        )
        hits = resp.get("hits", [])
        if not hits:
            break
        for h in hits:
            docs.append(h["document"])
        if len(docs) >= resp.get("found", 0):
            break
        page += 1
    return docs


def patch_schema(fields):
    """PATCH the collection schema (add/drop fields)."""
    return ts_request("PATCH", f"/collections/{COLLECTION}", {"fields": fields})


def upsert_document(doc):
    """Upsert (full replace) a single document via POST ?action=upsert."""
    return ts_request(
        "POST",
        f"/collections/{COLLECTION}/documents?action=upsert",
        doc,
    )


def get_schema():
    """Get the current collection schema."""
    return ts_request("GET", f"/collections/{COLLECTION}")


def print_schema_summary():
    schema = get_schema()
    print(f"  Collection: {schema['name']}, documents: {schema['num_documents']}")
    for f in schema["fields"]:
        dim = f.get("num_dim")
        dim_str = f" (num_dim={dim})" if dim else ""
        print(f"    - {f['name']}: {f['type']}{dim_str}")


def main():
    vectors_path = "/home/user/migration/new_vectors.jsonl"
    new_vectors = load_new_vectors(vectors_path)
    print(f"Loaded {len(new_vectors)} new 8-dim vectors from {vectors_path}")

    print("\n=== BEFORE MIGRATION ===")
    print_schema_summary()

    # ------------------------------------------------------------------
    # Step 1: Drop content_embedding (num_dim=4) from the schema
    # ------------------------------------------------------------------
    print("\n--- Step 1: Drop content_embedding (num_dim=4) ---")
    resp = patch_schema([{"name": "content_embedding", "drop": True}])
    if "message" in resp and "drop" not in str(resp):
        print(f"  FAILED: {resp['message']}", file=sys.stderr)
        sys.exit(1)
    print("  Dropped content_embedding from schema.")

    # ------------------------------------------------------------------
    # Step 2: Full-replace every document WITHOUT content_embedding
    #          to clear stale 4-dim data from the on-disk document store.
    # ------------------------------------------------------------------
    print("\n--- Step 2: Full-replace documents without content_embedding ---")
    docs = fetch_all_documents()
    print(f"  Fetched {len(docs)} documents.")
    for doc in docs:
        # Remove the old content_embedding; keep everything else
        cleaned = {k: v for k, v in doc.items() if k != "content_embedding"}
        resp = upsert_document(cleaned)
        if "id" not in resp:
            print(f"  FAILED to update doc {doc['id']}: {resp}", file=sys.stderr)
            sys.exit(1)
    print(f"  Replaced {len(docs)} documents (without content_embedding).")

    # ------------------------------------------------------------------
    # Step 3: Re-add content_embedding with num_dim=8 (optional)
    # ------------------------------------------------------------------
    print("\n--- Step 3: Re-add content_embedding with num_dim=8 ---")
    resp = patch_schema([
        {
            "name": "content_embedding",
            "type": "float[]",
            "num_dim": 8,
            "vec_dist": "cosine",
            "optional": True,
        }
    ])
    if "message" in resp and "fields" not in resp:
        print(f"  FAILED: {resp['message']}", file=sys.stderr)
        print("  Falling back to temporary-field strategy...", file=sys.stderr)
        fallback_strategy(new_vectors)
    else:
        print("  Re-added content_embedding with num_dim=8 (optional).")
        finish_migration(new_vectors)

    print("\n=== AFTER MIGRATION ===")
    print_schema_summary()


def finish_migration(new_vectors):
    """Step 4-5: Update all docs with 8-dim vectors, then tighten optional."""
    # ------------------------------------------------------------------
    # Step 4: Update every document with its new 8-dim content_embedding
    # ------------------------------------------------------------------
    print("\n--- Step 4: Update documents with 8-dim content_embedding ---")
    docs = fetch_all_documents()
    updated = 0
    for doc in docs:
        doc_id = doc["id"]
        if doc_id not in new_vectors:
            print(f"  WARNING: No new vector for doc {doc_id}", file=sys.stderr)
            continue
        doc["content_embedding"] = new_vectors[doc_id]
        resp = upsert_document(doc)
        if "id" not in resp:
            print(f"  FAILED to update doc {doc_id}: {resp}", file=sys.stderr)
            sys.exit(1)
        updated += 1
    print(f"  Updated {updated} documents with 8-dim vectors.")

    # ------------------------------------------------------------------
    # Step 5: (Optional) Make content_embedding non-optional
    #         All docs now have valid 8-dim vectors, so this should pass.
    # ------------------------------------------------------------------
    print("\n--- Step 5: Make content_embedding non-optional ---")
    # Drop and re-add as non-optional
    patch_schema([{"name": "content_embedding", "drop": True}])
    resp = patch_schema([
        {
            "name": "content_embedding",
            "type": "float[]",
            "num_dim": 8,
            "vec_dist": "cosine",
            "optional": False,
        }
    ])
    if "message" in resp and "fields" not in resp:
        print(f"  Could not make non-optional (stale data issue): {resp['message']}", file=sys.stderr)
        print("  Re-adding as optional instead...", file=sys.stderr)
        patch_schema([
            {
                "name": "content_embedding",
                "type": "float[]",
                "num_dim": 8,
                "vec_dist": "cosine",
                "optional": True,
            }
        ])
    print("  Done.")


def fallback_strategy(new_vectors):
    """
    If the simple drop-clear-readd approach fails because stale 4-dim data
    persists on disk, use a temporary field to hold the 8-dim vectors while
    we clear the old field.
    """
    print("\n=== FALLBACK: Temporary-field strategy ===")

    # a. Re-add content_embedding with num_dim=4 (restore original)
    print("\n--- Fallback a: Re-add content_embedding with num_dim=4 ---")
    patch_schema([
        {
            "name": "content_embedding",
            "type": "float[]",
            "num_dim": 4,
            "vec_dist": "cosine",
            "optional": False,
        }
    ])
    print("  Restored content_embedding (num_dim=4).")

    # b. Add temp field content_embedding_v2 with num_dim=8 (optional)
    print("\n--- Fallback b: Add content_embedding_v2 with num_dim=8 ---")
    resp = patch_schema([
        {
            "name": "content_embedding_v2",
            "type": "float[]",
            "num_dim": 8,
            "vec_dist": "cosine",
            "optional": True,
        }
    ])
    if "message" in resp and "fields" not in resp:
        print(f"  FAILED: {resp['message']}", file=sys.stderr)
        sys.exit(1)
    print("  Added content_embedding_v2 (num_dim=8, optional).")

    # c. Update all docs to populate content_embedding_v2
    print("\n--- Fallback c: Populate content_embedding_v2 ---")
    docs = fetch_all_documents()
    for doc in docs:
        doc_id = doc["id"]
        if doc_id in new_vectors:
            doc["content_embedding_v2"] = new_vectors[doc_id]
        resp = upsert_document(doc)
        if "id" not in resp:
            print(f"  FAILED: {resp}", file=sys.stderr)
            sys.exit(1)
    print(f"  Populated content_embedding_v2 for {len(docs)} docs.")

    # d. Drop content_embedding (4-dim)
    print("\n--- Fallback d: Drop content_embedding (4-dim) ---")
    patch_schema([{"name": "content_embedding", "drop": True}])
    print("  Dropped content_embedding.")

    # e. Full-replace all docs without content_embedding (clear stale data)
    print("\n--- Fallback e: Full-replace docs without content_embedding ---")
    docs = fetch_all_documents()
    for doc in docs:
        cleaned = {k: v for k, v in doc.items() if k != "content_embedding"}
        resp = upsert_document(cleaned)
        if "id" not in resp:
            print(f"  FAILED: {resp}", file=sys.stderr)
            sys.exit(1)
    print(f"  Replaced {len(docs)} docs (cleared content_embedding).")

    # f. Add content_embedding with num_dim=8 (optional)
    print("\n--- Fallback f: Add content_embedding with num_dim=8 ---")
    resp = patch_schema([
        {
            "name": "content_embedding",
            "type": "float[]",
            "num_dim": 8,
            "vec_dist": "cosine",
            "optional": True,
        }
    ])
    if "message" in resp and "fields" not in resp:
        print(f"  FAILED: {resp['message']}", file=sys.stderr)
        sys.exit(1)
    print("  Added content_embedding (num_dim=8, optional).")

    # g. Update all docs to populate content_embedding
    print("\n--- Fallback g: Populate content_embedding ---")
    docs = fetch_all_documents()
    for doc in docs:
        doc_id = doc["id"]
        if doc_id in new_vectors:
            doc["content_embedding"] = new_vectors[doc_id]
        resp = upsert_document(doc)
        if "id" not in resp:
            print(f"  FAILED: {resp}", file=sys.stderr)
            sys.exit(1)
    print(f"  Populated content_embedding for {len(docs)} docs.")

    # h. Drop content_embedding_v2
    print("\n--- Fallback h: Drop content_embedding_v2 ---")
    patch_schema([{"name": "content_embedding_v2", "drop": True}])
    print("  Dropped content_embedding_v2.")

    # i. Make content_embedding non-optional
    print("\n--- Fallback i: Make content_embedding non-optional ---")
    patch_schema([{"name": "content_embedding", "drop": True}])
    resp = patch_schema([
        {
            "name": "content_embedding",
            "type": "float[]",
            "num_dim": 8,
            "vec_dist": "cosine",
            "optional": False,
        }
    ])
    if "message" in resp and "fields" not in resp:
        print(f"  Could not make non-optional, re-adding as optional: {resp['message']}", file=sys.stderr)
        patch_schema([
            {
                "name": "content_embedding",
                "type": "float[]",
                "num_dim": 8,
                "vec_dist": "cosine",
                "optional": True,
            }
        ])
    print("  Done.")


if __name__ == "__main__":
    main()