import json
import os
import re
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/typesense-task"
DATA_DIR = os.path.join(PROJECT_DIR, "typesense-data")
ARTIFACT_PATH = os.path.join(PROJECT_DIR, "scoped_keys.json")
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"

HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
ADMIN_KEY = "xyz"
COLLECTION = "records"

EXPECTED_TENANT_COUNTS = {"acme": 3, "globex": 2, "initech": 4}
TOTAL_DOCS = sum(EXPECTED_TENANT_COUNTS.values())


def _server_healthy():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def typesense_server():
    """Ensure a Typesense server holding the persisted state is reachable.

    The task is a one-off job that starts its own server. If that server is
    still up we reuse it; otherwise we start a fresh server pointing at the
    already-populated data directory (collections and keys are persisted on
    disk and reload automatically). We do NOT recreate any task resources.
    """
    started_proc = None
    if not _server_healthy():
        log = open("/tmp/typesense_verifier.log", "w")
        started_proc = subprocess.Popen(
            [
                TYPESENSE_BINARY,
                f"--data-dir={DATA_DIR}",
                f"--api-key={ADMIN_KEY}",
                f"--port={PORT}",
                "--enable-cors",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if _server_healthy():
                break
            time.sleep(1)

    assert _server_healthy(), (
        f"Typesense server is not healthy at {BASE_URL}/health. "
        "Check /tmp/typesense_verifier.log for details."
    )

    yield

    if started_proc is not None:
        started_proc.terminate()
        try:
            started_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            started_proc.kill()


@pytest.fixture(scope="session")
def artifact():
    assert os.path.isfile(ARTIFACT_PATH), (
        f"Expected artifact file {ARTIFACT_PATH} does not exist."
    )
    with open(ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data


def _admin_headers():
    return {"X-TYPESENSE-API-KEY": ADMIN_KEY}


def _search(api_key, params):
    return requests.get(
        f"{BASE_URL}/collections/{COLLECTION}/documents/search",
        headers={"X-TYPESENSE-API-KEY": api_key},
        params=params,
        timeout=15,
    )


def test_artifact_shape(artifact):
    assert isinstance(artifact, dict), "scoped_keys.json must be a JSON object."
    for key in ("collection", "parent_search_key", "scoped_keys"):
        assert key in artifact, f"scoped_keys.json is missing required key '{key}'."
    assert artifact["collection"] == COLLECTION, (
        f"Expected 'collection' to be '{COLLECTION}', got {artifact['collection']!r}."
    )
    assert isinstance(artifact["parent_search_key"], str) and artifact["parent_search_key"], (
        "'parent_search_key' must be a non-empty string."
    )
    scoped = artifact["scoped_keys"]
    assert isinstance(scoped, dict), "'scoped_keys' must be a JSON object."
    assert set(scoped.keys()) == set(EXPECTED_TENANT_COUNTS.keys()), (
        f"Expected scoped keys for tenants {sorted(EXPECTED_TENANT_COUNTS)}, "
        f"got {sorted(scoped.keys())}."
    )
    for tenant, value in scoped.items():
        assert isinstance(value, str) and value, (
            f"Scoped key for tenant '{tenant}' must be a non-empty string."
        )


def test_collection_populated(typesense_server):
    resp = requests.get(
        f"{BASE_URL}/collections/{COLLECTION}",
        headers=_admin_headers(),
        timeout=15,
    )
    assert resp.status_code == 200, (
        f"Collection '{COLLECTION}' could not be retrieved (status {resp.status_code}): {resp.text}"
    )
    body = resp.json()
    assert body.get("num_documents") == TOTAL_DOCS, (
        f"Expected {TOTAL_DOCS} documents in '{COLLECTION}', got {body.get('num_documents')}."
    )
    field_names = {f.get("name"): f for f in body.get("fields", [])}
    assert "tenant_id" in field_names, "Collection schema is missing the 'tenant_id' field."
    assert field_names["tenant_id"].get("facet") is True, (
        "The 'tenant_id' field must be configured as a facet (filterable)."
    )


def _collection_scope_matches(collections):
    for entry in collections:
        if entry in (COLLECTION, "*"):
            return True
        try:
            if re.fullmatch(entry, COLLECTION):
                return True
        except re.error:
            continue
    return False


def test_parent_key_is_search_only(typesense_server, artifact):
    resp = requests.get(f"{BASE_URL}/keys", headers=_admin_headers(), timeout=15)
    assert resp.status_code == 200, (
        f"Failed to list API keys (status {resp.status_code}): {resp.text}"
    )
    keys = resp.json().get("keys", [])
    search_only_keys = [
        k
        for k in keys
        if k.get("actions") == ["documents:search"]
        and _collection_scope_matches(k.get("collections", []))
    ]
    assert search_only_keys, (
        "No search-only parent key (actions == ['documents:search'] scoped to "
        f"'{COLLECTION}') was found among the created keys."
    )
    parent_prefix = artifact["parent_search_key"][:4]
    prefixes = [k.get("value_prefix") for k in search_only_keys]
    assert parent_prefix in prefixes, (
        f"The parent_search_key prefix '{parent_prefix}' does not match any listed "
        f"search-only key prefix {prefixes}."
    )


def test_parent_key_cannot_write(typesense_server, artifact):
    resp = requests.post(
        f"{BASE_URL}/collections/{COLLECTION}/documents",
        headers={"X-TYPESENSE-API-KEY": artifact["parent_search_key"]},
        data=json.dumps(
            {
                "id": "intruder-doc",
                "tenant_id": "acme",
                "title": "should not be allowed",
                "category": "x",
                "secret_notes": "x",
            }
        ),
        timeout=15,
    )
    assert resp.status_code in (401, 403), (
        "The parent search-only key must not be able to create documents; "
        f"expected HTTP 401/403 but got {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize("tenant,expected_count", list(EXPECTED_TENANT_COUNTS.items()))
def test_scoped_key_returns_only_own_tenant(typesense_server, artifact, tenant, expected_count):
    scoped_key = artifact["scoped_keys"][tenant]
    resp = _search(scoped_key, {"q": "*", "query_by": "title", "per_page": 250})
    assert resp.status_code == 200, (
        f"Search with the '{tenant}' scoped key failed (status {resp.status_code}): {resp.text}"
    )
    body = resp.json()
    assert body.get("found") == expected_count, (
        f"Expected {expected_count} documents for tenant '{tenant}', got {body.get('found')}."
    )
    for hit in body.get("hits", []):
        doc = hit.get("document", {})
        assert doc.get("tenant_id") == tenant, (
            f"Scoped key for tenant '{tenant}' returned a document belonging to "
            f"'{doc.get('tenant_id')}'."
        )


def test_secret_notes_field_is_hidden(typesense_server, artifact):
    scoped_key = artifact["scoped_keys"]["acme"]
    resp = _search(scoped_key, {"q": "*", "query_by": "title", "per_page": 250})
    assert resp.status_code == 200, (
        f"Search with the 'acme' scoped key failed (status {resp.status_code}): {resp.text}"
    )
    body = resp.json()
    assert body.get("hits"), "Expected at least one hit for tenant 'acme'."
    for hit in body.get("hits", []):
        doc = hit.get("document", {})
        assert "secret_notes" not in doc, (
            "The 'secret_notes' field must be excluded from scoped-key search "
            f"responses, but it appeared in document {doc.get('id')}."
        )


def test_cross_tenant_override_is_blocked_acme(typesense_server, artifact):
    scoped_key = artifact["scoped_keys"]["acme"]
    resp = _search(
        scoped_key,
        {"q": "*", "query_by": "title", "filter_by": "tenant_id:=globex", "per_page": 250},
    )
    assert resp.status_code == 200, (
        f"Override search with the 'acme' scoped key failed (status {resp.status_code}): {resp.text}"
    )
    body = resp.json()
    assert body.get("found") == 0, (
        "The embedded tenant filter must prevent the 'acme' scoped key from "
        f"reading 'globex' data, but {body.get('found')} documents were returned."
    )


def test_cross_tenant_override_is_blocked_globex(typesense_server, artifact):
    scoped_key = artifact["scoped_keys"]["globex"]
    resp = _search(
        scoped_key,
        {"q": "*", "query_by": "title", "filter_by": "tenant_id:=acme", "per_page": 250},
    )
    assert resp.status_code == 200, (
        f"Override search with the 'globex' scoped key failed (status {resp.status_code}): {resp.text}"
    )
    body = resp.json()
    assert body.get("found") == 0, (
        "The embedded tenant filter must prevent the 'globex' scoped key from "
        f"reading 'acme' data, but {body.get('found')} documents were returned."
    )
