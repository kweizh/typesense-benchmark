#!/usr/bin/env python3
"""
Zero-downtime schema migration:
  products_v1  (rating: int32)  →  products_v2  (rating: float)
with alias swap and cleanup.
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8108"
API_KEY  = "xyz"
OLD_COLLECTION = "products_v1"
NEW_COLLECTION = "products_v2"
ALIAS          = "products"
LOG_FILE       = "/home/user/project/migration.log"


def api(method: str, path: str, body=None) -> dict | list | str:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "X-TYPESENSE-API-KEY": API_KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    # try JSON, fall back to raw text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_raw(method: str, path: str) -> bytes:
    """Return raw bytes (for JSONL export)."""
    url = BASE_URL + path
    req = urllib.request.Request(
        url, method=method,
        headers={"X-TYPESENSE-API-KEY": API_KEY},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def api_post_bytes(path: str, data: bytes, params: str = "") -> list:
    """POST bytes (JSONL body) and return a list of per-document result dicts."""
    url = BASE_URL + path + params
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "X-TYPESENSE-API-KEY": API_KEY,
            "Content-Type": "text/plain",
        },
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    # Response is JSONL — one JSON object per line
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            results.append(json.loads(line))
    return results


# ── 1. Fetch schema of products_v1 ──────────────────────────────────────────
print(f"[1] Fetching schema of '{OLD_COLLECTION}' …")
old_schema = api("GET", f"/collections/{OLD_COLLECTION}")
print(f"    num_documents = {old_schema['num_documents']}")

# ── 2. Build new schema (rating: int32 → float) ──────────────────────────────
print(f"[2] Building new schema for '{NEW_COLLECTION}' …")

new_fields = []
for f in old_schema["fields"]:
    field_def = {k: v for k, v in f.items()}
    if f["name"] == "rating":
        field_def["type"] = "float"
    new_fields.append(field_def)

new_schema = {
    "name": NEW_COLLECTION,
    "fields": new_fields,
    "default_sorting_field": old_schema.get("default_sorting_field", ""),
}
# preserve optional top-level settings if present
for key in ("enable_nested_fields", "token_separators", "symbols_to_index"):
    if key in old_schema and old_schema[key]:
        new_schema[key] = old_schema[key]

# ── 3. Create products_v2 ────────────────────────────────────────────────────
print(f"[3] Creating collection '{NEW_COLLECTION}' …")
# Drop if it already exists (idempotent re-run)
try:
    api("DELETE", f"/collections/{NEW_COLLECTION}")
    print(f"    (deleted pre-existing '{NEW_COLLECTION}')")
except urllib.error.HTTPError as e:
    if e.code != 404:
        raise

result = api("POST", "/collections", new_schema)
print(f"    Created: {result['name']}")

# Verify rating field type
for fld in result["fields"]:
    if fld["name"] == "rating":
        print(f"    rating.type = {fld['type']}")
        assert fld["type"] == "float", "rating field must be float!"

# ── 4. Export JSONL from products_v1 ─────────────────────────────────────────
print(f"[4] Exporting documents from '{OLD_COLLECTION}' …")
jsonl_bytes = api_raw("GET", f"/collections/{OLD_COLLECTION}/documents/export")
lines = [ln for ln in jsonl_bytes.splitlines() if ln.strip()]
doc_count = len(lines)
print(f"    Exported {doc_count} documents.")

# ── 5. Coerce rating values to float in the JSONL ────────────────────────────
print("[5] Coercing rating values to float …")
coerced_lines = []
for ln in lines:
    doc = json.loads(ln)
    if "rating" in doc:
        doc["rating"] = float(doc["rating"])
    coerced_lines.append(json.dumps(doc).encode())

coerced_jsonl = b"\n".join(coerced_lines)

# ── 6. Bulk-import into products_v2 ─────────────────────────────────────────
print(f"[6] Importing {doc_count} documents into '{NEW_COLLECTION}' …")
result_lines = api_post_bytes(
    f"/collections/{NEW_COLLECTION}/documents/import",
    coerced_jsonl,
    "?action=upsert",
)

failures = [r for r in result_lines if not r.get("success", False)]
if failures:
    print(f"    WARNING: {len(failures)} import failures:", file=sys.stderr)
    for f in failures[:5]:
        print(f"    {f}", file=sys.stderr)
    sys.exit(1)

print(f"    All {len(result_lines)} documents imported successfully.")

# Verify count
new_info = api("GET", f"/collections/{NEW_COLLECTION}")
assert new_info["num_documents"] == doc_count, (
    f"Document count mismatch: expected {doc_count}, got {new_info['num_documents']}"
)
print(f"    Verified num_documents = {new_info['num_documents']}")

# ── 7. Swap alias atomically ─────────────────────────────────────────────────
print(f"[7] Swapping alias '{ALIAS}' → '{NEW_COLLECTION}' …")
alias_result = api("PUT", f"/aliases/{ALIAS}", {"collection_name": NEW_COLLECTION})
assert alias_result["collection_name"] == NEW_COLLECTION, "Alias swap failed!"
print(f"    Alias '{ALIAS}' now points to '{alias_result['collection_name']}'")

# ── 8. Drop products_v1 ──────────────────────────────────────────────────────
print(f"[8] Dropping old collection '{OLD_COLLECTION}' …")
drop_result = api("DELETE", f"/collections/{OLD_COLLECTION}")
print(f"    Dropped: {drop_result['name']}")

# ── 9. Write migration log ───────────────────────────────────────────────────
print(f"[9] Writing migration log to '{LOG_FILE}' …")
with open(LOG_FILE, "w") as fh:
    fh.write(f"Migrated {doc_count} documents to {NEW_COLLECTION}\n")
    fh.write(f"Alias {ALIAS} -> {NEW_COLLECTION}\n")

print("[✓] Migration complete.")
print(f"    Migrated {doc_count} documents to {NEW_COLLECTION}")
print(f"    Alias {ALIAS} -> {NEW_COLLECTION}")
