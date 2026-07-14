import json
import os
import shutil
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/migration"
NEW_VECTORS_PATH = os.path.join(PROJECT_DIR, "new_vectors.jsonl")
TYPESENSE_URL = "http://localhost:8108"
START_SCRIPT = "/usr/local/bin/start-typesense.sh"
API_KEY = os.environ.get("TYPESENSE_API_KEY") or "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}


def _server_healthy() -> bool:
    try:
        resp = requests.get(f"{TYPESENSE_URL}/health", timeout=2)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except Exception:
        return False


def _ensure_server_running() -> None:
    if _server_healthy():
        return
    if os.path.exists(START_SCRIPT):
        subprocess.Popen(
            ["bash", START_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for _ in range(60):
        if _server_healthy():
            return
        time.sleep(1)


@pytest.fixture(scope="module", autouse=True)
def running_server():
    _ensure_server_running()
    yield


def test_requests_importable():
    assert requests is not None, "The 'requests' library must be importable."


def test_typesense_binary_available():
    assert shutil.which("typesense-server") is not None, (
        "typesense-server binary not found in PATH."
    )


def test_typesense_binary_executable():
    assert os.access("/usr/local/bin/typesense-server", os.X_OK), (
        "/usr/local/bin/typesense-server must exist and be executable."
    )


def test_start_helper_exists():
    assert os.path.isfile(START_SCRIPT), (
        f"Startup helper script {START_SCRIPT} does not exist."
    )


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_new_vectors_file_exists():
    assert os.path.isfile(NEW_VECTORS_PATH), (
        f"Pre-generated embeddings file {NEW_VECTORS_PATH} does not exist."
    )


def test_new_vectors_file_shape():
    with open(NEW_VECTORS_PATH) as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) == 8, (
        f"Expected 8 lines in {NEW_VECTORS_PATH}, found {len(lines)}."
    )
    for ln in lines:
        obj = json.loads(ln)
        assert "id" in obj, "Each new_vectors line must contain an 'id'."
        assert "content_embedding" in obj, (
            "Each new_vectors line must contain 'content_embedding'."
        )
        assert isinstance(obj["content_embedding"], list), (
            "'content_embedding' must be a list."
        )
        assert len(obj["content_embedding"]) == 8, (
            "Each pre-generated 'content_embedding' must have exactly 8 floats."
        )


def test_server_healthy():
    assert _server_healthy(), (
        "Typesense server is not healthy on http://localhost:8108."
    )


def test_notes_collection_exists():
    resp = requests.get(f"{TYPESENSE_URL}/collections/notes", headers=HEADERS, timeout=5)
    assert resp.status_code == 200, (
        f"Collection 'notes' must exist (GET returned {resp.status_code})."
    )
    schema = resp.json()
    assert schema.get("name") == "notes", "Collection name must be 'notes'."


def test_notes_has_4dim_vector_field():
    resp = requests.get(f"{TYPESENSE_URL}/collections/notes", headers=HEADERS, timeout=5)
    assert resp.status_code == 200, "Collection 'notes' must be retrievable."
    fields = {f["name"]: f for f in resp.json().get("fields", [])}
    assert "content_embedding" in fields, (
        "Collection 'notes' must have a 'content_embedding' field."
    )
    ce = fields["content_embedding"]
    assert ce.get("type") == "float[]", (
        "'content_embedding' must be of type 'float[]'."
    )
    assert ce.get("num_dim") == 4, (
        "Initially, 'content_embedding' must have num_dim == 4."
    )


def test_notes_has_eight_documents():
    resp = requests.get(f"{TYPESENSE_URL}/collections/notes", headers=HEADERS, timeout=5)
    assert resp.status_code == 200, "Collection 'notes' must be retrievable."
    assert resp.json().get("num_documents") == 8, (
        "Collection 'notes' must initially contain exactly 8 documents."
    )
