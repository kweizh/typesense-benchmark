import json
import os
import subprocess
import time

import pytest
import requests

# Connect over IPv4 explicitly. Using "localhost" can resolve to the IPv6 loopback
# (::1) while the Typesense server binds 127.0.0.1, causing confusing timeouts.
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"

PROJECT_DIR = "/home/user/typesense-rbac"
DATA_DIR = os.path.join(PROJECT_DIR, "typesense-data")
KEYS_PATH = os.path.join(PROJECT_DIR, "keys.json")
BOOTSTRAP_KEY = "xyz"
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"

DENIED_STATUSES = {401, 403}


def _health_ok():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except (requests.RequestException, ValueError):
        return False


def _wait_for_health(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _health_ok():
            return True
        time.sleep(1)
    return False


@pytest.fixture(scope="session", autouse=True)
def typesense_server():
    """Ensure a Typesense server is running on port 8108.

    If the executor's server is already healthy, reuse it. Otherwise start one
    against the persisted data directory (collections and keys survive on disk).
    """
    started_proc = None
    log_file = None
    if not _health_ok():
        os.makedirs(DATA_DIR, exist_ok=True)
        log_path = "/tmp/typesense_verify.log"
        log_file = open(log_path, "w")
        started_proc = subprocess.Popen(
            [
                TYPESENSE_BINARY,
                f"--data-dir={DATA_DIR}",
                f"--api-key={BOOTSTRAP_KEY}",
                f"--port={PORT}",
                "--enable-cors",
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        if not _wait_for_health(90):
            if log_file:
                log_file.flush()
                try:
                    with open(log_path) as f:
                        print(f.read())
                except OSError:
                    pass
            started_proc.terminate()
            pytest.fail("Typesense server did not become healthy on port 8108.")

    yield

    if started_proc is not None:
        started_proc.terminate()
        try:
            started_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            started_proc.kill()
    if log_file is not None:
        log_file.close()


def _headers(key):
    return {"X-TYPESENSE-API-KEY": key}


@pytest.fixture(scope="session")
def keys():
    assert os.path.isfile(KEYS_PATH), f"Expected key artifact at {KEYS_PATH}, but it does not exist."
    with open(KEYS_PATH) as f:
        data = json.load(f)
    return data


def test_keys_json_shape(keys):
    assert isinstance(keys, dict), f"{KEYS_PATH} must contain a JSON object, got {type(keys).__name__}."
    expected = {"search_only", "products_writer", "admin"}
    assert set(keys.keys()) == expected, (
        f"keys.json must contain exactly the keys {sorted(expected)}, got {sorted(keys.keys())}."
    )
    for name in expected:
        assert isinstance(keys[name], str) and keys[name].strip(), (
            f"Key '{name}' in keys.json must be a non-empty string."
        )
    values = [keys[name] for name in expected]
    assert len(set(values)) == 3, "The three API key values in keys.json must all be distinct."


def test_collections_exist_with_title_field():
    for coll in ("products", "orders"):
        resp = requests.get(f"{BASE_URL}/collections/{coll}", headers=_headers(BOOTSTRAP_KEY), timeout=10)
        assert resp.status_code == 200, (
            f"Collection '{coll}' should exist and be retrievable with the bootstrap key, got {resp.status_code}: {resp.text}"
        )
        schema = resp.json()
        fields = {f.get("name"): f.get("type") for f in schema.get("fields", [])}
        assert fields.get("title") == "string", (
            f"Collection '{coll}' must have a string field named 'title'; found fields: {fields}"
        )


# --- search_only key ---------------------------------------------------------

def test_search_only_allowed_search_products(keys):
    resp = requests.get(
        f"{BASE_URL}/collections/products/documents/search",
        params={"q": "*", "query_by": "title"},
        headers=_headers(keys["search_only"]),
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"search_only key should be allowed to search 'products' (expected 200), got {resp.status_code}: {resp.text}"
    )


def test_search_only_allowed_search_orders(keys):
    resp = requests.get(
        f"{BASE_URL}/collections/orders/documents/search",
        params={"q": "*", "query_by": "title"},
        headers=_headers(keys["search_only"]),
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"search_only key should be allowed to search 'orders' (expected 200), got {resp.status_code}: {resp.text}"
    )


def test_search_only_denied_write_document(keys):
    resp = requests.post(
        f"{BASE_URL}/collections/products/documents",
        params={"action": "upsert"},
        headers=_headers(keys["search_only"]),
        json={"id": "s1", "title": "nope"},
        timeout=10,
    )
    assert resp.status_code in DENIED_STATUSES, (
        f"search_only key must be denied (401/403) when writing a document, got {resp.status_code}: {resp.text}"
    )


def test_search_only_denied_create_collection(keys):
    resp = requests.post(
        f"{BASE_URL}/collections",
        headers=_headers(keys["search_only"]),
        json={"name": "blocked_by_search", "fields": [{"name": "title", "type": "string"}]},
        timeout=10,
    )
    assert resp.status_code in DENIED_STATUSES, (
        f"search_only key must be denied (401/403) when creating a collection, got {resp.status_code}: {resp.text}"
    )


def test_search_only_denied_list_keys(keys):
    resp = requests.get(f"{BASE_URL}/keys", headers=_headers(keys["search_only"]), timeout=10)
    assert resp.status_code in DENIED_STATUSES, (
        f"search_only key must be denied (401/403) when listing keys, got {resp.status_code}: {resp.text}"
    )


# --- products_writer key -----------------------------------------------------

def test_products_writer_allowed_upsert_and_effect(keys):
    resp = requests.post(
        f"{BASE_URL}/collections/products/documents",
        params={"action": "upsert"},
        headers=_headers(keys["products_writer"]),
        json={"id": "w1", "title": "writer-added"},
        timeout=10,
    )
    assert resp.status_code in (200, 201), (
        f"products_writer key should be allowed to upsert into 'products' (expected 200/201), got {resp.status_code}: {resp.text}"
    )
    # Confirm the write actually took effect, using the bootstrap key.
    check = requests.get(
        f"{BASE_URL}/collections/products/documents/w1",
        headers=_headers(BOOTSTRAP_KEY),
        timeout=10,
    )
    assert check.status_code == 200, (
        f"Document 'w1' written by products_writer should be retrievable (expected 200), got {check.status_code}: {check.text}"
    )
    assert check.json().get("title") == "writer-added", (
        f"Document 'w1' should have title 'writer-added', got: {check.text}"
    )


def test_products_writer_denied_write_other_collection(keys):
    resp = requests.post(
        f"{BASE_URL}/collections/orders/documents",
        params={"action": "upsert"},
        headers=_headers(keys["products_writer"]),
        json={"id": "o9", "title": "blocked"},
        timeout=10,
    )
    assert resp.status_code in DENIED_STATUSES, (
        f"products_writer key must be denied (401/403) when writing to 'orders', got {resp.status_code}: {resp.text}"
    )


def test_products_writer_denied_search(keys):
    resp = requests.get(
        f"{BASE_URL}/collections/products/documents/search",
        params={"q": "*", "query_by": "title"},
        headers=_headers(keys["products_writer"]),
        timeout=10,
    )
    assert resp.status_code in DENIED_STATUSES, (
        f"products_writer key must be denied (401/403) when searching 'products', got {resp.status_code}: {resp.text}"
    )


def test_products_writer_denied_create_collection(keys):
    resp = requests.post(
        f"{BASE_URL}/collections",
        headers=_headers(keys["products_writer"]),
        json={"name": "blocked_by_writer", "fields": [{"name": "title", "type": "string"}]},
        timeout=10,
    )
    assert resp.status_code in DENIED_STATUSES, (
        f"products_writer key must be denied (401/403) when creating a collection, got {resp.status_code}: {resp.text}"
    )


# --- admin key ---------------------------------------------------------------

def test_admin_allowed_search(keys):
    resp = requests.get(
        f"{BASE_URL}/collections/products/documents/search",
        params={"q": "*", "query_by": "title"},
        headers=_headers(keys["admin"]),
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"admin key should be allowed to search 'products' (expected 200), got {resp.status_code}: {resp.text}"
    )


def test_admin_allowed_list_keys(keys):
    resp = requests.get(f"{BASE_URL}/keys", headers=_headers(keys["admin"]), timeout=10)
    assert resp.status_code == 200, (
        f"admin key should be allowed to list keys (expected 200), got {resp.status_code}: {resp.text}"
    )


def test_admin_allowed_create_collection(keys):
    # Ensure idempotency across reruns: remove the collection first if present.
    requests.delete(f"{BASE_URL}/collections/admin_check", headers=_headers(BOOTSTRAP_KEY), timeout=10)
    resp = requests.post(
        f"{BASE_URL}/collections",
        headers=_headers(keys["admin"]),
        json={"name": "admin_check", "fields": [{"name": "title", "type": "string"}]},
        timeout=10,
    )
    assert resp.status_code == 201, (
        f"admin key should be allowed to create a collection (expected 201), got {resp.status_code}: {resp.text}"
    )


def test_admin_allowed_write_orders(keys):
    resp = requests.post(
        f"{BASE_URL}/collections/orders/documents",
        params={"action": "upsert"},
        headers=_headers(keys["admin"]),
        json={"id": "a1", "title": "admin-added"},
        timeout=10,
    )
    assert resp.status_code in (200, 201), (
        f"admin key should be allowed to write to 'orders' (expected 200/201), got {resp.status_code}: {resp.text}"
    )
