"""Idempotently provision the three Typesense collections and import the JSONL data.

Running this script more than once must succeed and leave the collections fully
populated with the latest data from the JSONL files in ``data/``.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("TYPESENSE_URL", "http://localhost:8108")
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
DATA_DIR = Path(__file__).resolve().parent / "data"

# (collection_name, schema_fields, jsonl_filename, id_field)
COLLECTIONS: list[tuple[str, list[dict], str, str]] = [
    (
        "products",
        [
            {"name": "product_name", "type": "string"},
            {"name": "category", "type": "string"},
            {"name": "price", "type": "float"},
        ],
        "products.jsonl",
        "id",
    ),
    (
        "articles",
        [
            {"name": "title", "type": "string"},
            {"name": "body", "type": "string"},
            {"name": "author", "type": "string"},
        ],
        "articles.jsonl",
        "id",
    ),
    (
        "users",
        [
            {"name": "username", "type": "string"},
            {"name": "full_name", "type": "string"},
            {"name": "bio", "type": "string"},
        ],
        "users.jsonl",
        "id",
    ),
]


def _request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE_URL}{path}"
    data = None
    headers = {"X-TYPESENSE-API-KEY": API_KEY}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload


def collection_exists(name: str) -> bool:
    status, _ = _request("GET", f"/collections/{name}")
    return status == 200


def delete_collection(name: str) -> None:
    """Best-effort delete. Ignores 404."""
    status, _ = _request("DELETE", f"/collections/{name}")
    if status not in (200, 404):
        raise RuntimeError(f"Failed to delete collection {name!r}: status={status}")


def create_collection(name: str, fields: list[dict]) -> None:
    status, payload = _request(
        "POST",
        "/collections",
        {"name": name, "fields": fields},
    )
    if status != 201:
        raise RuntimeError(
            f"Failed to create collection {name!r}: status={status} body={payload}"
        )


def load_documents(name: str, jsonl_path: Path) -> int:
    """Import documents from a JSONL file into ``name`` using the bulk import endpoint.

    Each document must include an ``id`` field. Returns the number of documents
    successfully imported (a 200 line with ``{"success": true}``).
    """
    documents: list[str] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            documents.append(line)

    body = ("\n".join(documents) + "\n").encode("utf-8")
    url = f"{BASE_URL}/collections/{name}/documents/import?action=create"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "X-TYPESENSE-API-KEY": API_KEY,
            "Content-Type": "application/x-ndjson",
        },
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")

    success_count = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("success"):
            success_count += 1
        else:
            print(
                f"  ! failed to import a document into {name!r}: {entry}",
                file=sys.stderr,
            )
    return success_count


def ensure_collection(name: str, fields: list[dict], jsonl_filename: str, id_field: str) -> None:
    jsonl_path = DATA_DIR / jsonl_filename
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Data file not found: {jsonl_path}")

    if collection_exists(name):
        # Idempotent: drop and recreate so the import is clean every run.
        print(f"  - collection {name!r} exists; deleting to reimport")
        delete_collection(name)

    print(f"  - creating collection {name!r}")
    create_collection(name, fields)

    print(f"  - importing {jsonl_filename} into {name!r}")
    count = load_documents(name, jsonl_path)
    print(f"  - imported {count} document(s) into {name!r}")


def verify_collections() -> None:
    """Sanity-check that each collection is reachable and non-empty."""
    for name, _, jsonl_filename, _ in COLLECTIONS:
        with (DATA_DIR / jsonl_filename).open("r", encoding="utf-8") as fh:
            expected = sum(1 for line in fh if line.strip())
        status, payload = _request("GET", f"/collections/{name}/documents/search?q=*&per_page=1")
        if status != 200:
            raise RuntimeError(
                f"Verification failed for {name!r}: status={status} body={payload}"
            )
        found = payload.get("found", 0)
        if found != expected:
            raise RuntimeError(
                f"Verification failed for {name!r}: expected {expected} docs, found {found}"
            )
        print(f"  - {name!r} OK ({found} documents)")


def main() -> int:
    print(f"Provisioning Typesense at {BASE_URL}")
    for name, fields, jsonl_filename, _id_field in COLLECTIONS:
        ensure_collection(name, fields, jsonl_filename, _id_field)
    print("Verifying collections...")
    verify_collections()
    print("Setup complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())