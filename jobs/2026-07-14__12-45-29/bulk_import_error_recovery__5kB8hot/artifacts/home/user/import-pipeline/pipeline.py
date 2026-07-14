#!/usr/bin/env python3
"""Resilient JSONL bulk-import pipeline for Typesense.

Reads /home/user/import-pipeline/data/raw_products.jsonl, bulk-imports it
into the `catalog` collection with `dirty_values=coerce_or_reject`, parses
the per-document import response, applies the two permitted repair rules
(currency-formatted price, missing category) to the failed documents,
re-imports the repaired subset, and writes /home/user/import-pipeline/report.json.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

TYPESENSE_HOST = "http://localhost:8108"
API_KEY = "xyz"
DATA_DIR = "/tmp/typesense-data"
TYPESENSE_BIN = "/usr/local/bin/typesense-server"

COLLECTION_NAME = "catalog"
INPUT_PATH = "/home/user/import-pipeline/data/raw_products.jsonl"
REPORT_PATH = "/home/user/import-pipeline/report.json"

SCHEMA = {
    "name": COLLECTION_NAME,
    "fields": [
        {"name": "sku", "type": "string"},
        {"name": "name", "type": "string"},
        {"name": "price", "type": "float"},
        {"name": "quantity", "type": "int32"},
        {"name": "category", "type": "string"},
    ],
}


# ---------------------------------------------------------------------------
# HTTP helpers (no external deps)
# ---------------------------------------------------------------------------

def _request(
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    query: str = "",
) -> tuple[int, bytes]:
    url = f"{TYPESENSE_HOST}{path}"
    if query:
        url = f"{url}?{query}"
    hdrs = {"X-TYPESENSE-API-KEY": API_KEY}
    if body is not None and "Content-Type" not in (headers or {}):
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _server_reachable() -> bool:
    try:
        status, body = _request("GET", "/health")
        return status == 200 and b'"ok":true' in body
    except Exception:
        return False


def ensure_server() -> None:
    """Make sure a Typesense server is reachable on localhost:8108."""
    if _server_reachable():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    # Start the server in the background.
    log_path = "/tmp/typesense.log"
    log_fh = open(log_path, "ab")
    subprocess.Popen(
        [
            TYPESENSE_BIN,
            "--data-dir", DATA_DIR,
            "--api-key", API_KEY,
            "--listen-port", "8108",
        ],
        stdout=log_fh,
        stderr=log_fh,
    )
    # Wait up to ~30s for it to come up.
    deadline = time.time() + 30
    while time.time() < deadline:
        if _server_reachable():
            return
        time.sleep(0.5)
    raise RuntimeError("Typesense server failed to start within 30 seconds")


def recreate_collection() -> None:
    """Drop and recreate the `catalog` collection to keep the run idempotent."""
    status, _ = _request("DELETE", f"/collections/{COLLECTION_NAME}")
    # 200 if existed, 404 if it didn't — both are fine.
    if status not in (200, 404):
        raise RuntimeError(f"Failed to delete collection: HTTP {status}")
    body = json.dumps(SCHEMA).encode("utf-8")
    status, resp = _request("POST", "/collections", body=body)
    if status != 201:
        raise RuntimeError(
            f"Failed to create collection: HTTP {status} body={resp!r}"
        )


# ---------------------------------------------------------------------------
# Import + repair
# ---------------------------------------------------------------------------

def bulk_import(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bulk-import documents; return the per-document response list."""
    payload = "\n".join(json.dumps(d, separators=(",", ":")) for d in documents)
    payload_bytes = payload.encode("utf-8")
    status, resp = _request(
        "POST",
        f"/collections/{COLLECTION_NAME}/documents/import",
        body=payload_bytes,
        headers={"Content-Type": "application/json"},
        query="action=upsert&dirty_values=coerce_or_reject",
    )
    if status != 200:
        raise RuntimeError(
            f"Import endpoint returned HTTP {status}: body={resp!r}"
        )
    text = resp.decode("utf-8")
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        results.append(json.loads(line))
    if len(results) != len(documents):
        raise RuntimeError(
            f"Import response length mismatch: got {len(results)} "
            f"results for {len(documents)} documents"
        )
    return results


def repair(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Apply the two permitted repair rules.

    Returns a repaired copy of the document, or None if no rule applies.
    """
    repaired = dict(doc)
    changed = False

    # Rule 1: currency-formatted price.
    price = repaired.get("price")
    if isinstance(price, str):
        # Strip currency symbols and thousands separators, then validate.
        normalized = re.sub(r"[^\d\.\-]", "", price)
        if normalized and normalized != price:
            try:
                float(normalized)
            except ValueError:
                return None
            repaired["price"] = float(normalized)
            changed = True

    # Rule 2: missing category.
    if "category" not in repaired or repaired.get("category") in (None, ""):
        if "category" not in repaired or repaired["category"] is None:
            repaired["category"] = "uncategorized"
            changed = True

    return repaired if changed else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ensure_server()
    recreate_collection()

    # Load input.
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw_docs: list[dict[str, Any]] = []
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw_docs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Malformed JSON on line {lineno} of {INPUT_PATH}: {e}"
                )
    total = len(raw_docs)

    # First pass.
    results = bulk_import(raw_docs)
    assert len(results) == total

    successes: list[dict[str, Any]] = []
    failed_sources: list[dict[str, Any]] = []
    for src, res in zip(raw_docs, results):
        if res.get("success") is True:
            successes.append(src)
        else:
            failed_sources.append(src)
    imported_first_pass = len(successes)

    # Apply repairs and re-import only the fixable subset.
    recovered: list[dict[str, Any]] = []
    remaining_failed: list[dict[str, Any]] = []
    to_reimport: list[dict[str, Any]] = []
    for doc in failed_sources:
        fixed = repair(doc)
        if fixed is None:
            remaining_failed.append(doc)
        else:
            to_reimport.append(fixed)

    if to_reimport:
        retry_results = bulk_import(to_reimport)
        for src, res in zip(to_reimport, retry_results):
            if res.get("success") is True:
                recovered.append(src)
            else:
                remaining_failed.append(src)

    recovered_count = len(recovered)
    failed_count = len(remaining_failed)

    # Sanity check the invariants.
    assert imported_first_pass + recovered_count + failed_count == total, (
        f"Count invariant broken: {imported_first_pass}+{recovered_count}+"
        f"{failed_count} != {total}"
    )

    # Verify the collection contents match the successes.
    status, body = _request(
        "GET", f"/collections/{COLLECTION_NAME}", query="exclude_fields=sku,name,price,quantity,category"
    )
    if status != 200:
        raise RuntimeError(f"Failed to fetch collection info: HTTP {status}")
    info = json.loads(body.decode("utf-8"))
    indexed = info.get("num_documents", 0)
    expected_indexed = imported_first_pass + recovered_count
    if indexed != expected_indexed:
        raise RuntimeError(
            f"Indexed document count {indexed} != expected {expected_indexed}"
        )

    # Build the report.
    report = {
        "total": total,
        "imported_first_pass": imported_first_pass,
        "recovered": recovered_count,
        "failed": failed_count,
        "recovered_ids": sorted(d["id"] for d in recovered),
        "failed_ids": sorted(d["id"] for d in remaining_failed),
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=False)
        f.write("\n")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())