import json
import os
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/import-pipeline"
REPORT_FILE = os.path.join(PROJECT_DIR, "report.json")
TYPESENSE_BIN = "/usr/local/bin/typesense-server"

HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}
COLLECTION = "catalog"

EXPECTED_TOTAL = 209
EXPECTED_FIRST_PASS = 202
EXPECTED_RECOVERED = 4
EXPECTED_FAILED = 3
EXPECTED_RECOVERED_IDS = ["f001", "f002", "f003", "f004"]
EXPECTED_FAILED_IDS = ["u001", "u002", "u003"]
EXPECTED_FINAL_COUNT = 206


def _healthy():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        return r.ok and r.json().get("ok") is True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def pipeline_run():
    """Ensure a Typesense server is running, then run the pipeline fresh."""
    started_proc = None
    if not _healthy():
        os.makedirs("/tmp/ts-verify-data", exist_ok=True)
        started_proc = subprocess.Popen(
            [
                TYPESENSE_BIN,
                "--data-dir=/tmp/ts-verify-data",
                f"--api-key={API_KEY}",
                f"--port={PORT}",
                "--enable-cors",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 60
        while time.time() < deadline and not _healthy():
            time.sleep(1)
        assert _healthy(), "Typesense server did not become healthy within 60s."

    # Remove any stale report so we verify a fresh, idempotent run.
    if os.path.isfile(REPORT_FILE):
        os.remove(REPORT_FILE)

    result = subprocess.run(
        ["python3", "pipeline.py"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    print("=== pipeline stdout ===")
    print(result.stdout)
    print("=== pipeline stderr ===")
    print(result.stderr)

    assert result.returncode == 0, (
        f"Pipeline command 'python3 pipeline.py' failed with exit code "
        f"{result.returncode}."
    )

    yield

    if started_proc is not None:
        started_proc.terminate()
        try:
            started_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            started_proc.kill()


@pytest.fixture(scope="session")
def report(pipeline_run):
    assert os.path.isfile(REPORT_FILE), (
        f"Report file {REPORT_FILE} was not created."
    )
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{REPORT_FILE} is not valid JSON: {exc}")


def _get_document(doc_id):
    return requests.get(
        f"{BASE_URL}/collections/{COLLECTION}/documents/{doc_id}",
        headers=HEADERS,
        timeout=10,
    )


def test_collection_schema(pipeline_run):
    r = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}", headers=HEADERS, timeout=10
    )
    assert r.status_code == 200, (
        f"Collection '{COLLECTION}' not found (status {r.status_code})."
    )
    data = r.json()
    field_types = {f["name"]: f["type"] for f in data.get("fields", [])}
    expected = {
        "sku": "string",
        "name": "string",
        "price": "float",
        "quantity": "int32",
        "category": "string",
    }
    for name, ftype in expected.items():
        assert name in field_types, (
            f"Expected field '{name}' to be defined in the '{COLLECTION}' schema."
        )
        assert field_types[name] == ftype, (
            f"Expected field '{name}' to have type '{ftype}', "
            f"got '{field_types[name]}'."
        )


def test_report_total(report):
    assert report.get("total") == EXPECTED_TOTAL, (
        f"Expected total == {EXPECTED_TOTAL}, got {report.get('total')}."
    )


def test_report_imported_first_pass(report):
    assert report.get("imported_first_pass") == EXPECTED_FIRST_PASS, (
        f"Expected imported_first_pass == {EXPECTED_FIRST_PASS}, "
        f"got {report.get('imported_first_pass')}."
    )


def test_report_recovered_count(report):
    assert report.get("recovered") == EXPECTED_RECOVERED, (
        f"Expected recovered == {EXPECTED_RECOVERED}, "
        f"got {report.get('recovered')}."
    )


def test_report_failed_count(report):
    assert report.get("failed") == EXPECTED_FAILED, (
        f"Expected failed == {EXPECTED_FAILED}, got {report.get('failed')}."
    )


def test_report_counts_consistent(report):
    total = report.get("total")
    parts = (
        report.get("imported_first_pass", 0)
        + report.get("recovered", 0)
        + report.get("failed", 0)
    )
    assert parts == total, (
        f"Report counts are inconsistent: imported_first_pass + recovered + "
        f"failed = {parts}, but total = {total}."
    )


def test_report_recovered_ids(report):
    ids = report.get("recovered_ids")
    assert ids == EXPECTED_RECOVERED_IDS, (
        f"Expected recovered_ids == {EXPECTED_RECOVERED_IDS} (sorted ascending), "
        f"got {ids}."
    )


def test_report_failed_ids(report):
    ids = report.get("failed_ids")
    assert ids == EXPECTED_FAILED_IDS, (
        f"Expected failed_ids == {EXPECTED_FAILED_IDS} (sorted ascending), "
        f"got {ids}."
    )


def test_final_collection_document_count(pipeline_run):
    r = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}", headers=HEADERS, timeout=10
    )
    assert r.status_code == 200, (
        f"Collection '{COLLECTION}' not found (status {r.status_code})."
    )
    num_docs = r.json().get("num_documents")
    assert num_docs == EXPECTED_FINAL_COUNT, (
        f"Expected {EXPECTED_FINAL_COUNT} documents in '{COLLECTION}', "
        f"got {num_docs}."
    )


def test_failed_documents_absent(pipeline_run):
    for doc_id in EXPECTED_FAILED_IDS:
        r = _get_document(doc_id)
        assert r.status_code == 404, (
            f"Failed document '{doc_id}' should NOT be indexed, but retrieval "
            f"returned status {r.status_code}."
        )


def test_recovered_currency_price_document(pipeline_run):
    r = _get_document("f001")
    assert r.status_code == 200, (
        f"Recovered document 'f001' should be indexed, got status {r.status_code}."
    )
    doc = r.json()
    assert doc.get("price") == pytest.approx(1299.0), (
        f"Expected f001 price to be normalized to 1299.0, got {doc.get('price')}."
    )
    assert doc.get("category") == "tech", (
        f"Expected f001 to preserve its original category 'tech', "
        f"got {doc.get('category')}."
    )


def test_recovered_missing_category_document(pipeline_run):
    r = _get_document("f003")
    assert r.status_code == 200, (
        f"Recovered document 'f003' should be indexed, got status {r.status_code}."
    )
    doc = r.json()
    assert doc.get("category") == "uncategorized", (
        f"Expected f003 category to default to 'uncategorized', "
        f"got {doc.get('category')}."
    )


def test_recovered_combined_document(pipeline_run):
    r = _get_document("f004")
    assert r.status_code == 200, (
        f"Recovered document 'f004' should be indexed, got status {r.status_code}."
    )
    doc = r.json()
    assert doc.get("price") == pytest.approx(59.5), (
        f"Expected f004 price to be normalized to 59.5, got {doc.get('price')}."
    )
    assert doc.get("category") == "uncategorized", (
        f"Expected f004 category to default to 'uncategorized', "
        f"got {doc.get('category')}."
    )


def test_first_pass_coercion_documents(pipeline_run):
    r1 = _get_document("c001")
    assert r1.status_code == 200, (
        f"Document 'c001' should be indexed on the first pass, "
        f"got status {r1.status_code}."
    )
    assert r1.json().get("price") == pytest.approx(45.5), (
        f"Expected c001 price to be coerced to 45.5, got {r1.json().get('price')}."
    )
    r2 = _get_document("c002")
    assert r2.status_code == 200, (
        f"Document 'c002' should be indexed on the first pass, "
        f"got status {r2.status_code}."
    )
    assert r2.json().get("price") == pytest.approx(1099.99), (
        f"Expected c002 price to be coerced to 1099.99, "
        f"got {r2.json().get('price')}."
    )
