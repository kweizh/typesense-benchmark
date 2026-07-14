import os
import subprocess
import time

import pytest
import requests

# Connect over IPv4 explicitly to avoid IPv6 loopback (::1) resolution issues.
HOST = "127.0.0.1"
TYPESENSE_URL = f"http://{HOST}:8108"
START_SCRIPT = "/usr/local/bin/start-typesense.sh"
API_KEY = os.environ.get("TYPESENSE_API_KEY") or "xyz"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

# Authoritative expected data (embedded in the verifier; do not trust the
# agent workspace for these values).
EXPECTED_DOCS = {
    "1": {"title": "Getting Started with Typesense", "category": "guide"},
    "2": {"title": "Understanding Vector Search", "category": "tutorial"},
    "3": {"title": "Typo Tolerance Explained", "category": "guide"},
    "4": {"title": "Faceted Navigation Basics", "category": "tutorial"},
    "5": {"title": "Scaling Search Clusters", "category": "ops"},
    "6": {"title": "Semantic Search with Embeddings", "category": "tutorial"},
    "7": {"title": "Zero Downtime Migrations", "category": "ops"},
    "8": {"title": "Filtering and Sorting Results", "category": "guide"},
}

EXPECTED_VECTORS = {
    "1": [0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18],
    "2": [0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28],
    "3": [0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38],
    "4": [0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48],
    "5": [0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58],
    "6": [0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68],
    "7": [0.71, 0.72, 0.73, 0.74, 0.75, 0.76, 0.77, 0.78],
    "8": [0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88],
}

TOL = 1e-4


def _server_healthy() -> bool:
    try:
        resp = requests.get(f"{TYPESENSE_URL}/health", timeout=2)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def running_server():
    if not _server_healthy() and os.path.exists(START_SCRIPT):
        subprocess.Popen(
            ["bash", START_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for _ in range(60):
        if _server_healthy():
            break
        time.sleep(1)
    assert _server_healthy(), (
        "Typesense server is not healthy on http://127.0.0.1:8108."
    )
    yield


def _get_schema():
    resp = requests.get(f"{TYPESENSE_URL}/collections/notes", headers=HEADERS, timeout=10)
    return resp


def test_collection_still_exists_in_place():
    resp = _get_schema()
    assert resp.status_code == 200, (
        f"Collection 'notes' must still exist in place (GET returned {resp.status_code})."
    )
    assert resp.json().get("name") == "notes", (
        "The collection must still be named 'notes' after the migration."
    )


def test_vector_field_migrated_to_8_dims():
    resp = _get_schema()
    assert resp.status_code == 200, "Collection 'notes' must be retrievable."
    fields = {f["name"]: f for f in resp.json().get("fields", [])}
    assert "content_embedding" in fields, (
        "The 'content_embedding' field must exist after migration."
    )
    ce = fields["content_embedding"]
    assert ce.get("type") == "float[]", (
        "'content_embedding' must be of type 'float[]'."
    )
    assert ce.get("num_dim") == 8, (
        f"'content_embedding' must have num_dim == 8, got {ce.get('num_dim')}."
    )


def test_non_vector_fields_intact():
    resp = _get_schema()
    assert resp.status_code == 200, "Collection 'notes' must be retrievable."
    fields = {f["name"]: f for f in resp.json().get("fields", [])}
    for name in ("title", "content", "category"):
        assert name in fields, f"The '{name}' field must still exist after migration."
        assert fields[name].get("type") == "string", (
            f"The '{name}' field must remain of type 'string'."
        )


def test_document_count_unchanged():
    resp = _get_schema()
    assert resp.status_code == 200, "Collection 'notes' must be retrievable."
    assert resp.json().get("num_documents") == 8, (
        f"Collection 'notes' must contain exactly 8 documents, "
        f"got {resp.json().get('num_documents')}."
    )


def test_documents_preserved():
    for doc_id, expected in EXPECTED_DOCS.items():
        resp = requests.get(
            f"{TYPESENSE_URL}/collections/notes/documents/{doc_id}",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200, (
            f"Document id {doc_id} must still exist (GET returned {resp.status_code})."
        )
        doc = resp.json()
        assert doc.get("title") == expected["title"], (
            f"Document {doc_id} title changed: expected {expected['title']!r}, "
            f"got {doc.get('title')!r}."
        )
        assert doc.get("category") == expected["category"], (
            f"Document {doc_id} category changed: expected {expected['category']!r}, "
            f"got {doc.get('category')!r}."
        )
        assert isinstance(doc.get("content"), str) and doc.get("content"), (
            f"Document {doc_id} must retain a non-empty 'content' string."
        )


def test_embeddings_regenerated_to_8_dims():
    for doc_id, expected_vec in EXPECTED_VECTORS.items():
        resp = requests.get(
            f"{TYPESENSE_URL}/collections/notes/documents/{doc_id}",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200, (
            f"Document id {doc_id} must be retrievable."
        )
        vec = resp.json().get("content_embedding")
        assert isinstance(vec, list), (
            f"Document {doc_id} 'content_embedding' must be a list."
        )
        assert len(vec) == 8, (
            f"Document {doc_id} 'content_embedding' must have 8 dimensions, "
            f"got {len(vec)}."
        )
        for i, (actual, want) in enumerate(zip(vec, expected_vec)):
            assert abs(float(actual) - want) <= TOL, (
                f"Document {doc_id} embedding[{i}] expected ~{want}, got {actual}."
            )


def test_vector_search_works():
    body = {
        "searches": [
            {
                "collection": "notes",
                "q": "*",
                "vector_query": (
                    "content_embedding:([0.11,0.12,0.13,0.14,0.15,0.16,0.17,0.18], k:5)"
                ),
                "exclude_fields": "content_embedding",
            }
        ]
    }
    resp = requests.post(
        f"{TYPESENSE_URL}/multi_search", headers=HEADERS, json=body, timeout=15
    )
    assert resp.status_code == 200, (
        f"multi_search must return 200, got {resp.status_code}: {resp.text}"
    )
    results = resp.json().get("results", [])
    assert results, "multi_search response must contain a 'results' array."
    result = results[0]
    assert result.get("found", 0) >= 1, (
        "Vector search must find at least one document."
    )
    hits = result.get("hits", [])
    assert hits, "Vector search must return at least one hit."
    for hit in hits:
        assert isinstance(hit.get("vector_distance"), (int, float)), (
            "Each hit must contain a numeric 'vector_distance'."
        )
    closest = min(hits, key=lambda h: h["vector_distance"])
    assert closest["document"]["id"] == "1", (
        "The closest hit to id 1's vector must be document id '1', "
        f"got {closest['document']['id']}."
    )
