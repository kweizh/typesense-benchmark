import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

import pytest

PROJECT_DIR = "/home/user/project"
DATA_DIR = "/home/user/project/typesense-data"
START_SCRIPT = "/home/user/project/start-typesense.sh"
BINARY_PATH = "/usr/local/bin/typesense-server"
BASE_URL = "http://localhost:8108"
API_KEY = "xyz"


def _request(method, path, timeout=10):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("X-TYPESENSE-API-KEY", API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _is_healthy():
    try:
        status, body = _request("GET", "/health", timeout=3)
        return status == 200 and '"ok":true' in body.replace(" ", "")
    except (urllib.error.URLError, OSError):
        return False


def _ensure_server_running():
    if _is_healthy():
        return
    assert os.path.isfile(START_SCRIPT), (
        f"Typesense start script {START_SCRIPT} does not exist; cannot bring the server up."
    )
    subprocess.Popen(
        ["bash", START_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if _is_healthy():
            return
        time.sleep(1)
    raise AssertionError("Typesense server did not become healthy within 60 seconds.")


@pytest.fixture(scope="module", autouse=True)
def server():
    _ensure_server_running()


def test_typesense_binary_available():
    assert os.path.isfile(BINARY_PATH) and os.access(BINARY_PATH, os.X_OK), (
        f"Typesense server binary not found or not executable at {BINARY_PATH}."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_data_directory_exists():
    assert os.path.isdir(DATA_DIR), (
        f"Typesense data directory {DATA_DIR} does not exist; seeded state is missing."
    )


def test_start_script_exists():
    assert os.path.isfile(START_SCRIPT), (
        f"Typesense start helper script {START_SCRIPT} does not exist."
    )


def test_alias_points_to_products_v1():
    status, body = _request("GET", "/aliases/products")
    assert status == 200, f"Alias 'products' should already exist, got HTTP {status}: {body}"
    data = json.loads(body)
    assert data.get("collection_name") == "products_v1", (
        f"Alias 'products' should initially point to 'products_v1', got {data.get('collection_name')!r}."
    )


def test_products_v1_collection_seeded():
    status, body = _request("GET", "/collections/products_v1")
    assert status == 200, f"Collection 'products_v1' should exist initially, got HTTP {status}: {body}"
    schema = json.loads(body)

    assert schema.get("num_documents") == 12, (
        f"Collection 'products_v1' should contain 12 seeded documents, got {schema.get('num_documents')}."
    )
    assert schema.get("default_sorting_field") == "rating", (
        f"'products_v1' default_sorting_field should be 'rating', got {schema.get('default_sorting_field')!r}."
    )

    fields = {f["name"]: f for f in schema.get("fields", [])}
    assert "rating" in fields, "Field 'rating' missing from 'products_v1' schema."
    assert fields["rating"]["type"] == "int32", (
        f"Field 'rating' should initially be type 'int32', got {fields['rating']['type']!r}."
    )
    assert fields.get("name", {}).get("type") == "string", "Field 'name' should be type 'string'."
    assert fields.get("category", {}).get("type") == "string", "Field 'category' should be type 'string'."
    assert fields.get("category", {}).get("facet") is True, "Field 'category' should be a facet."
    assert fields.get("price", {}).get("type") == "float", "Field 'price' should be type 'float'."
