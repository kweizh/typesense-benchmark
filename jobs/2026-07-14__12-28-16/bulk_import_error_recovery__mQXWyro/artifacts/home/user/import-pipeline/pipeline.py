#!/usr/bin/env python3
"""
Resilient JSONL Bulk-Import Pipeline for Typesense.

Reads a JSONL product dataset, bulk-imports it into a Typesense `catalog`
collection with dirty-value coercion enabled, inspects the per-document
results (Typesense always returns HTTP 200), repairs fixable failures with
two well-defined business rules, re-imports only the repaired documents, and
writes an accurate ingestion report.

The pipeline is idempotent: it recreates the `catalog` collection on every
run and uses upsert semantics, so repeated runs yield identical results.
"""

import json
import os
import re
import subprocess
import time
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TYPESENSE_URL = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION_NAME = "catalog"
DATA_DIR = "/tmp/typesense-data"
LOG_DIR = "/tmp/typesense-logs"
SERVER_BIN = "/usr/local/bin/typesense-server"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(PROJECT_DIR, "data", "raw_products.jsonl")
REPORT_PATH = os.path.join(PROJECT_DIR, "report.json")


# ---------------------------------------------------------------------------
# Typesense server management
# ---------------------------------------------------------------------------
def health_ok(timeout=2):
    try:
        with urllib.request.urlopen(
            TYPESENSE_URL + "/health", timeout=timeout
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("ok") is True
    except Exception:
        return False


def ensure_server():
    """Start a local Typesense server if one is not already reachable."""
    if health_ok():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    proc = subprocess.Popen(
        [
            SERVER_BIN,
            "--data-dir=" + DATA_DIR,
            "--api-key=" + API_KEY,
            "--api-port=8108",
            "--log-dir=" + LOG_DIR,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the server to become healthy.
    for _ in range(60):
        if health_ok():
            return
        time.sleep(0.5)
    raise RuntimeError("Typesense server did not become healthy in time")


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only, no third-party deps required)
# ---------------------------------------------------------------------------
def ts_request(method, path, body=None, content_type=None, params=None):
    url = TYPESENSE_URL + path
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode(params)

    data = None
    headers = {"X-Typesense-API-Key": API_KEY}
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            data = body.encode("utf-8") if isinstance(body, str) else body
            if content_type:
                headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------
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


def recreate_collection():
    # Delete the collection if it exists (ignore errors if it doesn't).
    ts_request("DELETE", "/collections/" + COLLECTION_NAME)
    status, body = ts_request("POST", "/collections", body=SCHEMA)
    if status not in (200, 201):
        raise RuntimeError("Failed to create collection: %d %s" % (status, body))


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------
def bulk_import(docs):
    """
    Import a list of dicts using the JSONL import endpoint with
    dirty_values=coerce_or_reject and upsert semantics.

    Returns a list of result dicts, one per input document, in input order.
    Each result dict has at least a 'success' boolean key.
    """
    if not docs:
        return []
    body = "\n".join(json.dumps(d) for d in docs)
    status, text = ts_request(
        "POST",
        "/collections/%s/documents/import" % COLLECTION_NAME,
        body=body,
        content_type="text/plain",
        params={"dirty_values": "coerce_or_reject", "action": "upsert"},
    )
    # Typesense always returns HTTP 200 for import; we must inspect the body.
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            # Treat an unparseable line as a failure for that document.
            results.append({"success": False, "error": "Unparseable response line"})
    # Sanity: result count should match input count.
    if len(results) != len(docs):
        # Pad/truncate defensively, but this should not happen.
        raise RuntimeError(
            "Import result count %d != input count %d" % (len(results), len(docs))
        )
    return results


# ---------------------------------------------------------------------------
# Repair rules
# ---------------------------------------------------------------------------
def repair_document(doc):
    """
    Apply the two allowed repair rules to a (copy of) the document.

    Rule 1 (currency-formatted price): when `price` is a string that is not
        directly numeric because it contains a currency symbol and/or thousands
        separators, normalize it to a plain number.
    Rule 2 (missing category): when the required `category` field is absent,
        set it to "uncategorized".

    Returns (repaired_doc, changed: bool). Only the two rules above are ever
    applied; any other defect is left untouched and will remain a failure.
    """
    repaired = dict(doc)
    changed = False

    # Rule 1: currency-formatted price.
    price = repaired.get("price")
    if isinstance(price, str):
        try:
            # Already directly numeric -> leave as-is (Typesense coerces it).
            float(price)
        except ValueError:
            # Not directly numeric: strip currency symbols and thousands
            # separators, then attempt to parse.
            cleaned = re.sub(r"[^\d.\-]", "", price.replace(",", ""))
            try:
                repaired["price"] = float(cleaned)
                changed = True
            except ValueError:
                pass  # Cannot repair this price; leave as-is (stays failed).

    # Rule 2: missing category.
    if "category" not in repaired:
        repaired["category"] = "uncategorized"
        changed = True

    return repaired, changed


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------
def load_dataset(path):
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    ensure_server()
    recreate_collection()

    docs = load_dataset(INPUT_PATH)
    total = len(docs)

    # --- First pass: bulk import everything with coercion enabled. ---
    first_results = bulk_import(docs)

    failed_indices = [
        i for i, r in enumerate(first_results) if not r.get("success", False)
    ]
    imported_first_pass = total - len(failed_indices)

    # --- Apply repair rules to the failed documents. ---
    repaired_docs = []          # docs that had at least one repair applied
    repaired_indices = []       # their original indices, parallel to repaired_docs
    unrepaired_indices = []     # failed docs with no applicable repair

    for i in failed_indices:
        repaired, changed = repair_document(docs[i])
        if changed:
            repaired_docs.append(repaired)
            repaired_indices.append(i)
        else:
            unrepaired_indices.append(i)

    # --- Second pass: re-import ONLY the repaired documents. ---
    second_results = bulk_import(repaired_docs) if repaired_docs else []

    recovered_indices = []
    still_failed_indices = list(unrepaired_indices)

    for idx, result in zip(repaired_indices, second_results):
        if result.get("success", False):
            recovered_indices.append(idx)
        else:
            still_failed_indices.append(idx)

    # --- Build the report. ---
    def doc_id(i):
        return docs[i].get("id")

    recovered_ids = sorted(d for d in (doc_id(i) for i in recovered_indices) if d)
    failed_ids = sorted(d for d in (doc_id(i) for i in still_failed_indices) if d)

    report = {
        "total": total,
        "imported_first_pass": imported_first_pass,
        "recovered": len(recovered_indices),
        "failed": len(still_failed_indices),
        "recovered_ids": recovered_ids,
        "failed_ids": failed_ids,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    # --- Verify consistency against the live collection. ---
    status, body = ts_request("GET", "/collections/%s" % COLLECTION_NAME)
    final_count = None
    if status == 200:
        try:
            final_count = json.loads(body).get("num_documents")
        except Exception:
            final_count = None

    expected_final = imported_first_pass + len(recovered_indices)
    consistency_ok = (
        imported_first_pass + len(recovered_indices) + len(still_failed_indices)
        == total
    )

    print(json.dumps(report, indent=2))
    print("Final collection document count: %s (expected %d)"
          % (final_count, expected_final))
    print("Count consistency: %s" % consistency_ok)

    if not consistency_ok:
        sys.exit(1)
    if final_count is not None and final_count != expected_final:
        sys.exit(1)


if __name__ == "__main__":
    main()