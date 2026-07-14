import json
import subprocess
import time

import pytest
import requests

HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

BINARY = "/usr/local/bin/typesense-server"
DATA_DIR = "/home/user/nested-search/typesense-data"
PROJECT_DIR = "/home/user/nested-search"
SEARCH_CLI = "/home/user/nested-search/search.py"
COLLECTION = "nested_orders"


def _health_ok():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def typesense_server():
    """Ensure a Typesense server is reachable on 127.0.0.1:8108.

    If one is already running (left by the executor), reuse it. Otherwise start
    a fresh server from the persisted data directory so the indexed collection
    is restored from disk.
    """
    proc = None
    if not _health_ok():
        proc = subprocess.Popen(
            [
                BINARY,
                f"--data-dir={DATA_DIR}",
                f"--api-key={API_KEY}",
                f"--port={PORT}",
                "--api-address=0.0.0.0",
                "--enable-cors",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if _health_ok():
                break
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                pytest.fail(f"Typesense server exited early:\n{out}")
            time.sleep(1)
        else:
            pytest.fail("Typesense server did not become healthy within 60s.")

    yield BASE_URL

    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _get_collection(typesense_server):
    resp = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Expected collection '{COLLECTION}' to exist (HTTP 200), "
        f"got {resp.status_code}: {resp.text}"
    )
    return resp.json()


def _field_by_name(schema, name):
    for field in schema.get("fields", []):
        if field.get("name") == name:
            return field
    return None


def test_nested_fields_enabled(typesense_server):
    schema = _get_collection(typesense_server)
    assert schema.get("enable_nested_fields") is True, (
        "Collection must be created with enable_nested_fields=true, "
        f"got: {schema.get('enable_nested_fields')!r}"
    )


def test_deep_attribute_color_field_typed_as_string_array(typesense_server):
    schema = _get_collection(typesense_server)
    field = _field_by_name(schema, "orders.line_items.attributes.color")
    assert field is not None, (
        "Deep nested field 'orders.line_items.attributes.color' must be "
        "explicitly defined in the schema."
    )
    assert field.get("type") == "string[]", (
        "Field 'orders.line_items.attributes.color' must be typed as 'string[]' "
        f"(fields inside arrays of objects become arrays), got: {field.get('type')!r}"
    )


def test_deep_category_field_is_faceted_string_array(typesense_server):
    schema = _get_collection(typesense_server)
    field = _field_by_name(schema, "orders.line_items.category")
    assert field is not None, (
        "Deep nested field 'orders.line_items.category' must be explicitly "
        "defined in the schema."
    )
    assert field.get("type") == "string[]", (
        "Field 'orders.line_items.category' must be typed as 'string[]', "
        f"got: {field.get('type')!r}"
    )
    assert field.get("facet") is True, (
        "Field 'orders.line_items.category' must be facetable (facet=true), "
        f"got: {field.get('facet')!r}"
    )


def test_all_documents_indexed(typesense_server):
    schema = _get_collection(typesense_server)
    assert schema.get("num_documents") == 4, (
        "Expected 4 documents indexed in the collection, "
        f"got: {schema.get('num_documents')!r}"
    )


def test_live_nested_search_filter_and_facet(typesense_server):
    params = {
        "q": "wireless",
        "query_by": "orders.line_items.name",
        "filter_by": "orders.line_items.attributes.color:=black",
        "facet_by": "orders.line_items.category",
        "per_page": 50,
    }
    resp = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}/documents/search",
        headers=HEADERS,
        params=params,
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"Nested search request failed (HTTP {resp.status_code}): {resp.text}"
    )
    body = resp.json()

    hit_ids = sorted(h["document"]["id"] for h in body.get("hits", []))
    assert hit_ids == ["cust_1", "cust_2"], (
        "Nested keyword search on 'orders.line_items.name' with deep attribute "
        f"filter should return cust_1 and cust_2, got: {hit_ids}"
    )

    facet_counts = body.get("facet_counts", [])
    category_facet = next(
        (f for f in facet_counts if f.get("field_name") == "orders.line_items.category"),
        None,
    )
    assert category_facet is not None, (
        "Expected facet_counts for 'orders.line_items.category' in the response."
    )
    counts = {c["value"]: c["count"] for c in category_facet.get("counts", [])}
    assert counts.get("Electronics") == 2, (
        f"Expected Electronics facet count of 2, got: {counts.get('Electronics')!r}"
    )
    assert counts.get("Kitchen") == 1, (
        f"Expected Kitchen facet count of 1, got: {counts.get('Kitchen')!r}"
    )


def _run_cli(keyword, color):
    result = subprocess.run(
        ["python3", SEARCH_CLI, "--keyword", keyword, "--color", color],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"search.py exited with code {result.returncode}. stderr: {result.stderr}"
    )
    stdout = result.stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Be lenient: the JSON object may be on the last non-empty line.
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        assert lines, f"search.py produced no output. Full stdout: {result.stdout!r}"
        return json.loads(lines[-1])


def test_cli_case_a_wireless_black(typesense_server):
    payload = _run_cli("wireless", "black")
    assert sorted(payload.get("matched_customer_ids", [])) == ["cust_1", "cust_2"], (
        f"Expected matched_customer_ids [cust_1, cust_2], got: {payload.get('matched_customer_ids')!r}"
    )
    assert payload.get("category_facet_counts") == {"Electronics": 2, "Kitchen": 1}, (
        f"Expected category_facet_counts {{Electronics:2, Kitchen:1}}, "
        f"got: {payload.get('category_facet_counts')!r}"
    )


def test_cli_case_b_ceramic_blue(typesense_server):
    payload = _run_cli("ceramic", "blue")
    assert sorted(payload.get("matched_customer_ids", [])) == ["cust_2", "cust_4"], (
        f"Expected matched_customer_ids [cust_2, cust_4], got: {payload.get('matched_customer_ids')!r}"
    )
    assert payload.get("category_facet_counts") == {"Kitchen": 2, "Electronics": 1}, (
        f"Expected category_facet_counts {{Kitchen:2, Electronics:1}}, "
        f"got: {payload.get('category_facet_counts')!r}"
    )


def test_cli_case_c_empty_result(typesense_server):
    payload = _run_cli("wireless", "silver")
    assert payload.get("matched_customer_ids", None) == [], (
        f"Expected empty matched_customer_ids, got: {payload.get('matched_customer_ids')!r}"
    )
    assert payload.get("category_facet_counts", None) == {}, (
        f"Expected empty category_facet_counts, got: {payload.get('category_facet_counts')!r}"
    )
