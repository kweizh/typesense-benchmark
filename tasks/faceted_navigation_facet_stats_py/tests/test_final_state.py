import json
import os
import socket
import subprocess

import pytest
import requests
from xprocess import ProcessStarter

PROJECT_DIR = "/home/user/facet-nav"
CLI = os.path.join(PROJECT_DIR, "facet_nav.py")
INDEXER = os.path.join(PROJECT_DIR, "index_data.py")

API_KEY = "xyz"
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
DATA_DIR = "/tmp/ts-verify-data"


@pytest.fixture(scope="session")
def typesense_server(xprocess):
    """Start the standalone Typesense server binary and wait until healthy."""
    os.makedirs(DATA_DIR, exist_ok=True)

    class Starter(ProcessStarter):
        name = "typesense_server"
        args = [
            "/usr/local/bin/typesense-server",
            f"--data-dir={DATA_DIR}",
            f"--api-key={API_KEY}",
            f"--port={PORT}",
            "--enable-cors",
        ]
        env = os.environ.copy()
        popen_kwargs = {"cwd": "/tmp", "text": True}
        timeout = 120
        terminate_on_interrupt = True

        def startup_check(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((HOST, PORT)) != 0:
                    return False
            try:
                resp = requests.get(f"{BASE_URL}/health", timeout=10)
                return resp.status_code == 200 and resp.json().get("ok") is True
            except (requests.RequestException, ValueError):
                return False

    info = xprocess.getinfo(Starter.name)
    printed = 0

    def capture_logs(tag):
        nonlocal printed
        try:
            with open(info.logpath, "r") as f:
                lines = f.readlines()
        except OSError:
            lines = []
        new = lines[printed:]
        printed = len(lines)
        print(f"===== [{tag}] typesense_server log begin =====")
        print("".join(new))
        print(f"===== [{tag}] typesense_server log end =====")

    started = False
    try:
        xprocess.ensure(Starter.name, Starter)
        started = True
    finally:
        capture_logs("STARTED" if started else "FAILED")

    yield BASE_URL

    capture_logs("TEARDOWN")
    info.terminate()


@pytest.fixture(scope="session")
def indexed(typesense_server):
    """Run the executor's indexing entry point and confirm a clean, populated index."""
    assert os.path.isfile(INDEXER), f"Indexing entry point not found at {INDEXER}."
    result = subprocess.run(
        ["python3", INDEXER],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=120,
    )
    print("index_data.py stdout:\n", result.stdout)
    print("index_data.py stderr:\n", result.stderr)
    assert result.returncode == 0, (
        f"index_data.py exited with {result.returncode}: {result.stderr}"
    )

    resp = requests.get(
        f"{BASE_URL}/collections/products",
        headers={"X-TYPESENSE-API-KEY": API_KEY},
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"'products' collection was not created (status {resp.status_code}): {resp.text}"
    )
    num_docs = resp.json().get("num_documents")
    assert num_docs == 12, (
        f"Expected 'products' collection to contain 12 documents, found {num_docs}."
    )
    return BASE_URL


def run_cli(payload):
    assert os.path.isfile(CLI), f"Query CLI not found at {CLI}."
    proc = subprocess.run(
        ["python3", CLI],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"facet_nav.py failed for input {payload!r} "
        f"(exit {proc.returncode}). stderr: {proc.stderr}"
    )
    stdout = proc.stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"facet_nav.py did not print a single JSON object for input {payload!r}: "
            f"{exc}. Raw stdout: {proc.stdout!r}"
        )


def facet_map(response, field):
    assert "facets" in response, f"Response missing 'facets': {response}"
    assert field in response["facets"], (
        f"Response facets missing field '{field}': {response['facets']}"
    )
    result = {}
    for entry in response["facets"][field]:
        result[entry["value"]] = entry["count"]
    return result


def assert_price_stats(response, expected):
    assert "price_stats" in response, f"Response missing 'price_stats': {response}"
    stats = response["price_stats"]
    for key, value in expected.items():
        assert key in stats, f"price_stats missing key '{key}': {stats}"
        assert abs(float(stats[key]) - value) <= 0.01, (
            f"price_stats['{key}'] expected ~{value}, got {stats[key]}."
        )


def test_baseline_no_filters(indexed):
    resp = run_cli({"q": "*"})
    assert resp.get("found") == 12, f"Expected found=12, got {resp.get('found')}."
    assert facet_map(resp, "brand") == {
        "Apple": 3,
        "Dell": 3,
        "Samsung": 3,
        "Sony": 2,
        "HP": 1,
    }, f"Unexpected brand facet counts: {facet_map(resp, 'brand')}"
    assert facet_map(resp, "category") == {
        "Laptops": 6,
        "Phones": 2,
        "TVs": 2,
        "Headphones": 1,
        "Monitors": 1,
    }, f"Unexpected category facet counts: {facet_map(resp, 'category')}"
    assert facet_map(resp, "tags") == {
        "premium": 8,
        "portable": 6,
        "budget": 2,
        "home": 2,
        "pro": 1,
        "audio": 1,
    }, f"Unexpected tags facet counts: {facet_map(resp, 'tags')}"
    assert_price_stats(
        resp, {"min": 299.0, "max": 1999.0, "sum": 12888.0, "avg": 1074.0}
    )


def test_single_filter_disjunctive(indexed):
    resp = run_cli({"q": "*", "filters": {"category": ["Laptops"]}})
    assert resp.get("found") == 6, f"Expected found=6, got {resp.get('found')}."
    assert facet_map(resp, "brand") == {
        "Apple": 2,
        "Dell": 2,
        "HP": 1,
        "Samsung": 1,
    }, f"Brand facet should reflect the category filter: {facet_map(resp, 'brand')}"
    assert facet_map(resp, "category") == {
        "Laptops": 6,
        "Phones": 2,
        "TVs": 2,
        "Headphones": 1,
        "Monitors": 1,
    }, (
        "Category facet must ignore its own filter (disjunctive): "
        f"{facet_map(resp, 'category')}"
    )
    assert_price_stats(
        resp, {"min": 599.0, "max": 1999.0, "sum": 7194.0, "avg": 1199.0}
    )


def test_multi_field_multi_select(indexed):
    resp = run_cli(
        {"q": "*", "filters": {"category": ["Laptops"], "brand": ["Apple"]}}
    )
    assert resp.get("found") == 2, f"Expected found=2, got {resp.get('found')}."
    assert facet_map(resp, "brand") == {
        "Apple": 2,
        "Dell": 2,
        "HP": 1,
        "Samsung": 1,
    }, (
        "Brand facet must ignore its own filter but respect category=Laptops: "
        f"{facet_map(resp, 'brand')}"
    )
    assert facet_map(resp, "category") == {
        "Laptops": 2,
        "Phones": 1,
    }, (
        "Category facet must ignore its own filter but respect brand=Apple: "
        f"{facet_map(resp, 'category')}"
    )
    assert_price_stats(
        resp, {"min": 999.0, "max": 1999.0, "sum": 2998.0, "avg": 1499.0}
    )


def test_facet_query_prefix(indexed):
    resp = run_cli({"q": "*", "facet_query": {"field": "brand", "prefix": "sa"}})
    assert "facet_query_matches" in resp, (
        f"Response must include 'facet_query_matches': {resp}"
    )
    matches = {entry["value"]: entry["count"] for entry in resp["facet_query_matches"]}
    assert matches == {"Samsung": 3}, (
        f"Expected only Samsung (count 3) for prefix 'sa', got {matches}."
    )


def test_max_facet_values_cap(indexed):
    resp = run_cli({"q": "*", "filters": {}, "max_facet_values": 2})
    brand = resp["facets"]["brand"]
    assert len(brand) == 2, (
        f"max_facet_values=2 should return exactly 2 brand values, got {len(brand)}."
    )
    counts = sorted((entry["count"] for entry in brand), reverse=True)
    assert counts == [3, 3], (
        f"The two returned brand values should have the highest counts (3, 3), got {counts}."
    )


def test_price_range_filter(indexed):
    resp = run_cli({"q": "*", "filters": {"price": {"min": 1000, "max": 2000}}})
    assert resp.get("found") == 5, f"Expected found=5, got {resp.get('found')}."
    assert_price_stats(
        resp, {"min": 1299.0, "max": 1999.0, "sum": 7995.0, "avg": 1599.0}
    )
    assert facet_map(resp, "brand") == {
        "Apple": 1,
        "Dell": 1,
        "HP": 1,
        "Sony": 1,
        "Samsung": 1,
    }, (
        "Brand facet must reflect the price filter (different field): "
        f"{facet_map(resp, 'brand')}"
    )


def test_keyword_query(indexed):
    resp = run_cli({"q": "dell"})
    assert resp.get("found") == 3, f"Expected found=3, got {resp.get('found')}."
    assert facet_map(resp, "brand") == {"Dell": 3}, (
        f"Keyword query 'dell' should yield only Dell products: {facet_map(resp, 'brand')}"
    )
