"""
Resilient JSONL Bulk-Import Pipeline for Typesense
====================================================
Steps:
  1. Ensure Typesense is reachable; (re)create the `catalog` collection.
  2. Bulk-import all source documents with dirty_values=coerce_or_reject.
  3. Parse per-document results; collect every failed source document.
  4. Apply repair rules to fixable documents; re-import only those.
  5. Write report.json.

Repair rules (the ONLY transformations allowed):
  R1 – Currency-formatted price: strip currency symbols / thousands separators
       so the value becomes a valid float.
  R2 – Missing category: set to "uncategorized".
"""

import json
import os
import re
import subprocess
import sys
import time

import urllib.request
import urllib.error

# ── Configuration ────────────────────────────────────────────────────────────
TYPESENSE_URL = "http://localhost:8108"
API_KEY       = "xyz"
COLLECTION    = "catalog"
DATA_PATH     = os.path.join(os.path.dirname(__file__), "data", "raw_products.jsonl")
REPORT_PATH   = os.path.join(os.path.dirname(__file__), "report.json")
TYPESENSE_BIN = "/usr/local/bin/typesense-server"
DATA_DIR      = "/home/user/typesense-data"

HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method: str, path: str, body: bytes | None = None,
             content_type: str = "application/json") -> tuple[int, bytes]:
    url = TYPESENSE_URL + path
    hdrs = {"X-TYPESENSE-API-KEY": API_KEY}
    if body is not None:
        hdrs["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def get(path: str) -> tuple[int, dict]:
    status, raw = _request("GET", path)
    return status, json.loads(raw)


def post_json(path: str, obj: dict) -> tuple[int, dict]:
    body = json.dumps(obj).encode()
    status, raw = _request("POST", path, body)
    return status, json.loads(raw)


def delete(path: str) -> tuple[int, dict]:
    status, raw = _request("DELETE", path)
    return status, json.loads(raw)


def post_jsonl(path: str, lines: list[str]) -> tuple[int, str]:
    """POST a JSONL payload; returns (http_status, raw_text_body)."""
    body = ("\n".join(lines) + "\n").encode()
    status, raw = _request("POST", path, body, "text/plain")
    return status, raw.decode()

# ── Typesense server management ───────────────────────────────────────────────

def ensure_server_running():
    """Start typesense-server if not already reachable."""
    for _ in range(3):
        try:
            status, _ = get("/health")
            if status == 200:
                print("[server] Typesense is reachable at", TYPESENSE_URL)
                return
        except Exception:
            pass
        time.sleep(1)

    print("[server] Typesense not reachable – starting it …")
    os.makedirs(DATA_DIR, exist_ok=True)
    subprocess.Popen(
        [
            TYPESENSE_BIN,
            f"--data-dir={DATA_DIR}",
            f"--api-key={API_KEY}",
            "--listen-port=8108",
            "--enable-cors",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # wait up to 20 s for it to become healthy
    for _ in range(20):
        time.sleep(1)
        try:
            status, body = get("/health")
            if status == 200 and body.get("ok"):
                print("[server] Typesense started successfully.")
                return
        except Exception:
            pass
    sys.exit("[server] ERROR: could not start/reach Typesense after 20 s.")

# ── Collection management ─────────────────────────────────────────────────────

SCHEMA = {
    "name": COLLECTION,
    "fields": [
        {"name": "sku",      "type": "string"},
        {"name": "name",     "type": "string"},
        {"name": "price",    "type": "float"},
        {"name": "quantity", "type": "int32"},
        {"name": "category", "type": "string"},
    ],
}


def recreate_collection():
    """Drop the collection if it exists, then create it fresh."""
    status, _ = get(f"/collections/{COLLECTION}")
    if status == 200:
        print(f"[collection] Dropping existing '{COLLECTION}' collection …")
        delete(f"/collections/{COLLECTION}")

    print(f"[collection] Creating '{COLLECTION}' collection …")
    status, body = post_json("/collections", SCHEMA)
    if status not in (200, 201):
        sys.exit(f"[collection] ERROR creating collection: {body}")
    print("[collection] Collection created.")

# ── Dataset loading ───────────────────────────────────────────────────────────

def load_documents(path: str) -> list[dict]:
    docs = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"[load] JSON parse error on line {lineno}: {exc}")
    return docs

# ── Import helpers ────────────────────────────────────────────────────────────

IMPORT_URL = f"/collections/{COLLECTION}/documents/import"


def bulk_import(docs: list[dict], action: str = "upsert") -> list[dict]:
    """
    POST docs to the import endpoint with dirty_values=coerce_or_reject.
    Returns a list of per-document result dicts (same order as input).
    """
    lines = [json.dumps(d) for d in docs]
    url   = f"{IMPORT_URL}?action={action}&dirty_values=coerce_or_reject"
    http_status, raw_body = post_jsonl(url, lines)

    # The API always returns 200; per-document results are in the JSONL body.
    result_lines = [l for l in raw_body.splitlines() if l.strip()]
    if len(result_lines) != len(docs):
        sys.exit(
            f"[import] Mismatch: sent {len(docs)} docs, got {len(result_lines)} result lines"
        )
    return [json.loads(l) for l in result_lines]

# ── Repair logic ──────────────────────────────────────────────────────────────

# R1 – strip currency symbol and thousands separators from a price string
_CURRENCY_RE = re.compile(r"^[^\d]*?([\d,]+\.?\d*)$")


def _try_repair_price(raw_price) -> float | None:
    """
    If raw_price is a string that can become a valid float after removing
    currency symbols and commas, return the float; else return None.
    """
    if isinstance(raw_price, (int, float)):
        return None  # already numeric – no repair needed
    if not isinstance(raw_price, str):
        return None
    # Remove currency symbol(s) and thousands separators
    cleaned = re.sub(r"[^\d.]", "", raw_price)
    try:
        return float(cleaned)
    except ValueError:
        return None


def try_repair(doc: dict) -> dict | None:
    """
    Apply the two allowed repair rules to *doc*.
    Returns the repaired document, or None if the doc cannot be fully repaired.

    Rules:
      R1 – currency-formatted price  → strip symbols / commas
      R2 – missing category          → set to "uncategorized"

    Any other defect makes the document unrepairable (return None).
    """
    repaired = dict(doc)
    changed  = False

    # R1: price is a non-numeric string with currency/comma formatting
    raw_price = repaired.get("price")
    if isinstance(raw_price, str):
        fixed = _try_repair_price(raw_price)
        if fixed is not None:
            repaired["price"] = fixed
            changed = True
        else:
            # Price string that we cannot normalise → unrepairable
            return None

    # R2: missing category
    if "category" not in repaired:
        repaired["category"] = "uncategorized"
        changed = True

    return repaired if changed else None


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    # ── Step 0: server & collection ──────────────────────────────────────────
    ensure_server_running()
    recreate_collection()

    # ── Step 1: load source documents ───────────────────────────────────────
    source_docs = load_documents(DATA_PATH)
    total = len(source_docs)
    print(f"[pipeline] Loaded {total} documents from {DATA_PATH}")

    # ── Step 2: first-pass bulk import ──────────────────────────────────────
    print("[pipeline] Running first-pass import …")
    first_results = bulk_import(source_docs, action="upsert")

    first_pass_ok:     list[dict] = []
    first_pass_failed: list[dict] = []  # (source_doc, result) pairs

    for doc, res in zip(source_docs, first_results):
        if res.get("success"):
            first_pass_ok.append(doc)
        else:
            first_pass_failed.append(doc)

    imported_first_pass = len(first_pass_ok)
    print(
        f"[pipeline] First pass: {imported_first_pass} ok, "
        f"{len(first_pass_failed)} failed"
    )

    # ── Step 3: repair & second-pass import ─────────────────────────────────
    to_retry:     list[dict] = []   # repaired documents
    retry_source: list[dict] = []   # matching original documents
    permanently_failed: list[dict] = []

    for doc in first_pass_failed:
        repaired = try_repair(doc)
        if repaired is not None:
            to_retry.append(repaired)
            retry_source.append(doc)
        else:
            permanently_failed.append(doc)

    recovered_ids:     list[str] = []
    still_failed_docs: list[dict] = list(permanently_failed)

    if to_retry:
        print(f"[pipeline] Retrying {len(to_retry)} repaired document(s) …")
        retry_results = bulk_import(to_retry, action="upsert")

        for orig_doc, repaired_doc, res in zip(retry_source, to_retry, retry_results):
            if res.get("success"):
                recovered_ids.append(str(orig_doc["id"]))
            else:
                print(
                    f"[pipeline] Repair attempt failed for id={orig_doc.get('id')}: "
                    f"{res.get('error', '?')}"
                )
                still_failed_docs.append(orig_doc)

    recovered  = len(recovered_ids)
    failed     = len(still_failed_docs)
    failed_ids = sorted(str(d["id"]) for d in still_failed_docs)

    # ── Step 4: consistency check ────────────────────────────────────────────
    assert imported_first_pass + recovered + failed == total, (
        f"Count mismatch: {imported_first_pass} + {recovered} + {failed} != {total}"
    )

    # ── Step 5: write report ─────────────────────────────────────────────────
    report = {
        "total":               total,
        "imported_first_pass": imported_first_pass,
        "recovered":           recovered,
        "failed":              failed,
        "recovered_ids":       sorted(recovered_ids),
        "failed_ids":          failed_ids,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print("\n── Report ──────────────────────────────────────────────────────")
    print(json.dumps(report, indent=2))
    print("────────────────────────────────────────────────────────────────")
    print(f"[pipeline] Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
