import os
import re
import subprocess
import time

import pytest
import requests

HOST = "127.0.0.1"
BASE_URL = f"http://{HOST}:8108"
API_KEY = "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

PROJECT_DIR = "/home/user/project"
START_SCRIPT = "/home/user/project/start-typesense.sh"
LOG_FILE = "/home/user/project/migration.log"


def _is_healthy():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except (requests.RequestException, ValueError):
        return False


@pytest.fixture(scope="session", autouse=True)
def ensure_server():
    """Make the Typesense server reachable so its persisted state can be inspected.

    Starting the server only reloads on-disk state; it does not repeat the migration.
    """
    if not _is_healthy():
        assert os.path.isfile(START_SCRIPT), (
            f"Typesense start script {START_SCRIPT} not found; cannot inspect final state."
        )
        subprocess.Popen(
            ["bash", START_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 60
        while time.time() < deadline and not _is_healthy():
            time.sleep(1)
    assert _is_healthy(), "Typesense server did not become healthy within 60 seconds."


@pytest.fixture(scope="session")
def new_collection(ensure_server):
    """Resolve the physical collection the `products` alias now points to."""
    resp = requests.get(f"{BASE_URL}/aliases/products", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, (
        f"Alias 'products' should exist, got HTTP {resp.status_code}: {resp.text}"
    )
    target = resp.json().get("collection_name")
    assert target and target != "products_v1", (
        f"Alias 'products' must point to a NEW collection (not 'products_v1'), got {target!r}."
    )
    return target


def test_alias_swapped_to_new_collection(new_collection):
    assert new_collection != "products_v1", (
        f"Alias 'products' must no longer point to 'products_v1', but points to {new_collection!r}."
    )


def test_old_collection_dropped():
    resp = requests.get(f"{BASE_URL}/collections/products_v1", headers=HEADERS, timeout=10)
    assert resp.status_code == 404, (
        f"Old collection 'products_v1' should be dropped (expected HTTP 404), got HTTP {resp.status_code}: {resp.text}"
    )


def test_new_collection_schema(new_collection):
    resp = requests.get(f"{BASE_URL}/collections/{new_collection}", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, (
        f"New collection {new_collection!r} should exist, got HTTP {resp.status_code}: {resp.text}"
    )
    schema = resp.json()
    fields = {f["name"]: f for f in schema.get("fields", [])}

    assert "rating" in fields, f"Field 'rating' missing from {new_collection!r} schema."
    assert fields["rating"]["type"] == "float", (
        f"Field 'rating' must be type 'float' after migration, got {fields['rating']['type']!r}."
    )
    assert fields.get("name", {}).get("type") == "string", "Field 'name' should be type 'string'."
    assert fields.get("category", {}).get("type") == "string", "Field 'category' should be type 'string'."
    assert fields.get("category", {}).get("facet") is True, "Field 'category' should remain a facet."
    assert fields.get("price", {}).get("type") == "float", "Field 'price' should be type 'float'."
    assert schema.get("default_sorting_field") == "rating", (
        f"default_sorting_field should remain 'rating', got {schema.get('default_sorting_field')!r}."
    )


def test_no_data_loss_count(new_collection):
    resp = requests.get(f"{BASE_URL}/collections/{new_collection}", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, f"Failed to retrieve {new_collection!r}: {resp.text}"
    num_docs = resp.json().get("num_documents")
    assert num_docs == 12, (
        f"New collection must contain all 12 migrated documents, got num_documents={num_docs}."
    )


def _get_doc(new_collection, doc_id):
    resp = requests.get(
        f"{BASE_URL}/collections/{new_collection}/documents/{doc_id}",
        headers=HEADERS,
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"Document id={doc_id} should exist in {new_collection!r}, got HTTP {resp.status_code}: {resp.text}"
    )
    return resp.json()


def test_documents_preserved(new_collection):
    doc7 = _get_doc(new_collection, "7")
    assert doc7.get("name") == "Standing Desk", f"doc 7 name mismatch: {doc7.get('name')!r}"
    assert doc7.get("category") == "Office", f"doc 7 category mismatch: {doc7.get('category')!r}"
    assert doc7.get("price") == 299.0, f"doc 7 price mismatch: {doc7.get('price')!r}"
    assert doc7.get("rating") == 5, f"doc 7 rating should be 5, got {doc7.get('rating')!r}"

    doc3 = _get_doc(new_collection, "3")
    assert doc3.get("name") == "USB-C Cable", f"doc 3 name mismatch: {doc3.get('name')!r}"
    assert doc3.get("category") == "Electronics", f"doc 3 category mismatch: {doc3.get('category')!r}"
    assert doc3.get("price") == 9.5, f"doc 3 price mismatch: {doc3.get('price')!r}"
    assert doc3.get("rating") == 3, f"doc 3 rating should be 3, got {doc3.get('rating')!r}"

    doc6 = _get_doc(new_collection, "6")
    assert doc6.get("name") == "Notebook", f"doc 6 name mismatch: {doc6.get('name')!r}"
    assert doc6.get("rating") == 2, f"doc 6 rating should be 2, got {doc6.get('rating')!r}"


def _search(collection, filter_by=None):
    params = {"q": "*", "query_by": "name"}
    if filter_by is not None:
        params["filter_by"] = filter_by
    resp = requests.get(
        f"{BASE_URL}/collections/{collection}/documents/search",
        headers=HEADERS,
        params=params,
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"Search on {collection!r} failed with HTTP {resp.status_code}: {resp.text}"
    )
    return resp.json()


def test_float_filtering_functional(new_collection):
    high = _search(new_collection, filter_by="rating:>4.5")
    assert high.get("found") == 4, (
        f"filter_by rating:>4.5 should match the 4 documents with rating 5, got found={high.get('found')}."
    )
    all_docs = _search(new_collection, filter_by="rating:>=2.0")
    assert all_docs.get("found") == 12, (
        f"filter_by rating:>=2.0 should match all 12 documents, got found={all_docs.get('found')}."
    )


def test_search_through_alias(new_collection):
    result = _search("products")
    assert result.get("found") == 12, (
        f"Searching through alias 'products' should return all 12 migrated documents, got found={result.get('found')}."
    )


def test_migration_log(new_collection):
    assert os.path.isfile(LOG_FILE), f"Migration log file {LOG_FILE} does not exist."
    with open(LOG_FILE) as f:
        content = f.read()
    assert re.search(rf"Migrated\s+12\s+documents\s+to\s+{re.escape(new_collection)}", content), (
        f"Log must contain 'Migrated 12 documents to {new_collection}'. Got:\n{content}"
    )
    assert re.search(rf"Alias\s+products\s+->\s+{re.escape(new_collection)}", content), (
        f"Log must contain 'Alias products -> {new_collection}'. Got:\n{content}"
    )
