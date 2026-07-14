import os
import subprocess
import time

import pytest
import requests

HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

PROJECT_DIR = "/home/user/typesense-curation"
DATA_DIR = os.path.join(PROJECT_DIR, "typesense-data")
BINARY = "/usr/local/bin/typesense-server"
LOG_FILE = os.path.join(PROJECT_DIR, "setup.log")

COLLECTION = "catalog"


def _health_ok():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def typesense_server():
    """Ensure the Typesense server configured by the task is online.

    The executor is expected to leave the server running. If it is not
    reachable, bring the persisted state (collection + overrides stored in the
    data directory) back online WITHOUT recreating any resources.
    """
    proc = None
    if not _health_ok():
        proc = subprocess.Popen(
            [
                BINARY,
                f"--data-dir={DATA_DIR}",
                f"--api-key={API_KEY}",
                f"--port={PORT}",
                "--enable-cors",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if _health_ok():
                break
            time.sleep(1)

    assert _health_ok(), (
        f"Typesense server is not healthy at {BASE_URL}/health. It must be "
        "running with the configured collection and overrides."
    )

    yield

    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _get_overrides(_server):
    resp = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}/overrides", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Failed to list overrides (status {resp.status_code}): {resp.text}"
    )
    return resp.json().get("overrides", [])


def _search_hits(query, extra_params):
    params = {"q": query, "query_by": "name", "per_page": 20}
    params.update(extra_params)
    resp = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}/documents/search",
        headers=HEADERS,
        params=params,
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"Search for q='{query}' failed (status {resp.status_code}): {resp.text}"
    )
    return resp.json().get("hits", [])


def _ids(hits):
    return [h["document"]["id"] for h in hits]


def test_collection_exists_with_documents(typesense_server):
    resp = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Collection '{COLLECTION}' not found (status {resp.status_code}): {resp.text}"
    )
    data = resp.json()
    assert data.get("num_documents") == 7, (
        f"Expected 7 documents in '{COLLECTION}', got {data.get('num_documents')}."
    )
    brand_fields = [f for f in data.get("fields", []) if f.get("name") == "brand"]
    assert brand_fields, "Field 'brand' is missing from the collection schema."
    assert brand_fields[0].get("facet") is True, (
        "Field 'brand' must be defined as facetable (facet: true)."
    )


def test_three_overrides_registered(typesense_server):
    overrides = _get_overrides(typesense_server)
    assert len(overrides) == 3, (
        f"Expected exactly 3 override rules, found {len(overrides)}: "
        f"{[o.get('id') for o in overrides]}"
    )


def test_exact_phone_override_definition(typesense_server):
    overrides = _get_overrides(typesense_server)
    exact_rules = [
        o
        for o in overrides
        if o.get("rule", {}).get("match") == "exact"
        and o.get("rule", {}).get("query") == "phone"
    ]
    assert len(exact_rules) == 1, (
        "Expected exactly one exact-match override with rule.query == 'phone'."
    )
    rule = exact_rules[0]

    includes = {i["id"]: i.get("position") for i in rule.get("includes", [])}
    assert includes.get("p1") == 1, "Exact override must pin document 'p1' to position 1."
    assert includes.get("p7") == 2, "Exact override must pin document 'p7' to position 2."

    excludes = {e["id"] for e in rule.get("excludes", [])}
    assert "p2" in excludes, "Exact override must exclude document 'p2'."


def test_contains_deal_override_definition(typesense_server):
    overrides = _get_overrides(typesense_server)
    contains_rules = [
        o
        for o in overrides
        if o.get("rule", {}).get("match") == "contains"
        and o.get("rule", {}).get("query") == "deal"
    ]
    assert len(contains_rules) == 1, (
        "Expected exactly one contains-match override with rule.query == 'deal'."
    )
    includes = {i["id"]: i.get("position") for i in contains_rules[0].get("includes", [])}
    assert includes.get("p3") == 1, "Contains 'deal' override must pin 'p3' to position 1."


def test_dynamic_brand_filter_override_definition(typesense_server):
    overrides = _get_overrides(typesense_server)
    dynamic_rules = [
        o
        for o in overrides
        if "{brand}" in (o.get("filter_by") or "")
        and o.get("rule", {}).get("query") == "{brand} phone"
    ]
    assert len(dynamic_rules) == 1, (
        "Expected exactly one dynamic-filter override whose rule.query is "
        "'{brand} phone' and whose filter_by contains the '{brand}' placeholder."
    )


def test_exact_match_pinning_and_hiding(typesense_server):
    hits = _search_hits("phone", {"sort_by": "popularity:desc"})
    ids = _ids(hits)
    assert ids[:1] == ["p1"], f"Expected first result to be 'p1', got order: {ids}"
    assert ids[:2] == ["p1", "p7"], f"Expected first two results 'p1','p7', got: {ids}"
    assert "p2" not in ids, f"Excluded document 'p2' must not appear, got: {ids}"
    assert ids == ["p1", "p7", "p3", "p4", "p5", "p6"], (
        f"Unexpected curated result order for q='phone': {ids}"
    )


def test_contains_match_pinning(typesense_server):
    ids = _ids(_search_hits("deal", {}))
    assert ids[:1] == ["p3"], (
        f"Expected 'p3' pinned first for q='deal', got order: {ids}"
    )
    assert "p6" in ids, f"Naturally matching document 'p6' must be present, got: {ids}"


def test_dynamic_brand_filtering(typesense_server):
    hits = _search_hits("Samsung phone", {})
    ids = _ids(hits)
    assert ids, "Query 'Samsung phone' returned no results; dynamic filter likely broken."
    brands = {h["document"]["brand"] for h in hits}
    assert brands == {"Samsung"}, (
        f"All hits for 'Samsung phone' must have brand 'Samsung', got brands: {brands}"
    )
    assert "p2" in ids, f"Samsung document 'p2' must be present, got: {ids}"
    assert "p3" not in ids and "p7" not in ids, (
        f"Non-Samsung documents must be filtered out, got: {ids}"
    )


def test_setup_log_lists_override_ids(typesense_server):
    assert os.path.isfile(LOG_FILE), f"Log file {LOG_FILE} does not exist."
    with open(LOG_FILE) as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    assert len(lines) == 3, (
        f"Expected 3 non-empty override id lines in the log, got {len(lines)}: {lines}"
    )
    override_ids = {o.get("id") for o in _get_overrides(typesense_server)}
    for line in lines:
        assert line in override_ids, (
            f"Log line '{line}' does not match any registered override id: {override_ids}"
        )
