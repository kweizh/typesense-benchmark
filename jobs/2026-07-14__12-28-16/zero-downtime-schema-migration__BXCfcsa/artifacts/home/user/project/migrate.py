#!/usr/bin/env python3
"""Zero-downtime schema migration for Typesense: rating int32 -> float via alias swap."""

import json
import urllib.request
import urllib.error
import sys

BASE = "http://localhost:8108"
API_KEY = "xyz"
ALIAS_NAME = "products"
OLD_COLLECTION = "products_v1"
NEW_COLLECTION = "products_v2"
LOG_FILE = "/home/user/project/migration.log"


def api(method, path, body=None, raw=None, content_type="application/json"):
    url = f"{BASE}{path}"
    headers = {"X-TYPESENSE-API-KEY": API_KEY}
    data = None
    if raw is not None:
        data = raw.encode("utf-8") if isinstance(raw, str) else raw
        headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, text
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main():
    # 1. Verify server health
    status, body = api("GET", "/health")
    if status != 200 or json.loads(body).get("ok") is not True:
        print(f"Server not healthy: {status} {body}", file=sys.stderr)
        sys.exit(1)
    print("Server is healthy.")

    # 2. Resolve the alias to confirm the current physical collection
    status, body = api("GET", f"/aliases/{ALIAS_NAME}")
    if status != 200:
        print(f"Could not read alias {ALIAS_NAME}: {status} {body}", file=sys.stderr)
        sys.exit(1)
    alias_info = json.loads(body)
    current_collection = alias_info["collection_name"]
    print(f"Alias '{ALIAS_NAME}' currently points to '{current_collection}'.")
    if current_collection != OLD_COLLECTION:
        print(f"Warning: expected '{OLD_COLLECTION}' but alias points to "
              f"'{current_collection}'. Proceeding with '{current_collection}'.")
        src_collection = current_collection
    else:
        src_collection = OLD_COLLECTION

    # 3. Fetch the schema of the source collection
    status, body = api("GET", f"/collections/{src_collection}")
    if status != 200:
        print(f"Could not fetch collection {src_collection}: {status} {body}",
              file=sys.stderr)
        sys.exit(1)
    schema = json.loads(body)
    src_doc_count = schema["num_documents"]
    print(f"Source collection '{src_collection}' has {src_doc_count} documents.")
    print(f"Original schema fields: "
          f"{json.dumps(schema['fields'], indent=2)}")

    # 4. Build the new schema: identical except rating type -> float
    new_fields = []
    for f in schema["fields"]:
        nf = dict(f)
        if nf["name"] == "rating":
            nf["type"] = "float"
        new_fields.append(nf)

    create_body = {
        "name": NEW_COLLECTION,
        "fields": new_fields,
        "default_sorting_field": schema.get("default_sorting_field", ""),
    }
    # Preserve optional schema-level settings if present
    if "enable_nested_fields" in schema:
        create_body["enable_nested_fields"] = schema["enable_nested_fields"]
    if "symbols_to_index" in schema:
        create_body["symbols_to_index"] = schema["symbols_to_index"]
    if "token_separators" in schema:
        create_body["token_separators"] = schema["token_separators"]

    print(f"New collection schema fields: "
          f"{json.dumps(create_body['fields'], indent=2)}")

    # 5. Create the new collection (drop first if a stale one exists)
    status, body = api("DELETE", f"/collections/{NEW_COLLECTION}")
    if status == 200:
        print(f"Deleted pre-existing '{NEW_COLLECTION}' before recreating.")
    status, body = api("POST", "/collections", body=create_body)
    if status not in (200, 201):
        print(f"Failed to create collection {NEW_COLLECTION}: {status} {body}",
              file=sys.stderr)
        sys.exit(1)
    print(f"Created new collection '{NEW_COLLECTION}'.")

    # 6. Export all documents from the source collection (JSONL)
    status, export = api("GET", f"/collections/{src_collection}/documents/export")
    if status != 200:
        print(f"Export failed: {status} {export}", file=sys.stderr)
        sys.exit(1)

    export_lines = [ln for ln in export.splitlines() if ln.strip()]
    export_count = len(export_lines)
    print(f"Exported {export_count} documents from '{src_collection}'.")
    if export_count != src_doc_count:
        print(f"Warning: source reports {src_doc_count} docs but exported "
              f"{export_count} lines.", file=sys.stderr)

    # 7. Import documents into the new collection (bulk JSONL import).
    #    Typesense coerces int32 -> float automatically during import.
    status, body = api("POST", f"/collections/{NEW_COLLECTION}/documents/import",
                       raw=export, content_type="text/plain")
    if status != 200:
        print(f"Import failed: {status} {body}", file=sys.stderr)
        sys.exit(1)
    # The import endpoint returns one JSON object per document indicating success.
    import_lines = [ln for ln in body.splitlines() if ln.strip()]
    failed = [ln for ln in import_lines if '"success":false' in ln]
    if failed:
        print(f"Import had {len(failed)} failures: {failed[:5]}", file=sys.stderr)
        sys.exit(1)
    imported_count = len(import_lines)
    print(f"Imported {imported_count} documents into '{NEW_COLLECTION}'.")

    # 8. Verify the new collection's document count and rating type
    status, body = api("GET", f"/collections/{NEW_COLLECTION}")
    if status != 200:
        print(f"Could not verify new collection: {status} {body}", file=sys.stderr)
        sys.exit(1)
    new_schema = json.loads(body)
    new_doc_count = new_schema["num_documents"]
    rating_type = next(f["type"] for f in new_schema["fields"]
                       if f["name"] == "rating")
    print(f"New collection has {new_doc_count} documents; "
          f"rating type is '{rating_type}'.")
    if rating_type != "float":
        print(f"ERROR: rating type is {rating_type}, expected float.",
              file=sys.stderr)
        sys.exit(1)
    if new_doc_count != src_doc_count:
        print(f"ERROR: document count mismatch: source={src_doc_count} "
              f"new={new_doc_count}", file=sys.stderr)
        sys.exit(1)

    migrated_count = new_doc_count

    # 9. Atomically swap the alias to point to the new collection
    status, body = api("PUT", f"/aliases/{ALIAS_NAME}",
                       body={"collection_name": NEW_COLLECTION})
    if status != 200:
        print(f"Failed to swap alias: {status} {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Alias '{ALIAS_NAME}' now points to '{NEW_COLLECTION}'.")

    # 10. Delete the old collection
    status, body = api("DELETE", f"/collections/{src_collection}")
    if status != 200:
        print(f"Failed to delete old collection {src_collection}: "
              f"{status} {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Deleted old collection '{src_collection}'.")

    # 11. Write the migration report
    with open(LOG_FILE, "w") as fh:
        fh.write(f"Migrated {migrated_count} documents to {NEW_COLLECTION}\n")
        fh.write(f"Alias products -> {NEW_COLLECTION}\n")
    print(f"Migration report written to {LOG_FILE}.")

    # 12. Final verification
    status, body = api("GET", f"/aliases/{ALIAS_NAME}")
    final_alias = json.loads(body)
    print(f"\n=== FINAL STATE ===")
    print(f"Alias '{ALIAS_NAME}' -> '{final_alias['collection_name']}'")
    status, body = api("GET", "/collections")
    cols = json.loads(body)
    names = [c["name"] for c in cols]
    print(f"Collections present: {names}")
    assert final_alias["collection_name"] == NEW_COLLECTION
    assert src_collection not in names
    assert NEW_COLLECTION in names
    print("Migration completed successfully.")


if __name__ == "__main__":
    main()