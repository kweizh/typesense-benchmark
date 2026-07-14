import json
import os
import re
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/typesense-ranking"
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"
DATA_DIR = os.path.join(PROJECT_DIR, "typesense-data")
API_KEY = "xyz"
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}


def _server_healthy():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except (requests.RequestException, ValueError):
        return False


@pytest.fixture(scope="session")
def typesense_server():
    """Ensure a Typesense server is running on port 8108.

    If one is already healthy (e.g. started by the executor), reuse it.
    Otherwise start a fresh standalone binary and tear it down afterwards.
    """
    if _server_healthy():
        yield
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    proc = subprocess.Popen(
        [
            TYPESENSE_BINARY,
            f"--data-dir={DATA_DIR}",
            f"--api-key={API_KEY}",
            f"--port={PORT}",
            "--enable-cors",
        ],
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + 60
    healthy = False
    while time.time() < deadline:
        if _server_healthy():
            healthy = True
            break
        if proc.poll() is not None:
            break
        time.sleep(1)

    if not healthy:
        out = ""
        if proc.poll() is not None and proc.stdout is not None:
            out = proc.stdout.read()
        proc.terminate()
        raise RuntimeError(f"Typesense server failed to become healthy.\n{out}")

    yield

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def seeded(typesense_server):
    """Run the executor's setup entrypoint to (re)create and populate the collection."""
    result = subprocess.run(
        ["python3", "setup.py"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        "Running 'python3 setup.py' failed with exit code "
        f"{result.returncode}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    yield


def _run_rank(query):
    result = subprocess.run(
        ["python3", "rank.py", "--query", query],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"'python3 rank.py --query {query!r}' failed with exit code "
        f"{result.returncode}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    stdout = result.stdout.strip()
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", stdout, re.DOTALL)
        assert match is not None, (
            f"rank.py did not print a JSON array. Got stdout:\n{result.stdout}"
        )
        parsed = json.loads(match.group(0))
    assert isinstance(parsed, list), (
        f"rank.py output should be a JSON array, got: {parsed!r}"
    )
    return [str(x) for x in parsed]


def test_collection_indexed(seeded):
    """The catalog collection must be really populated with all 6 documents."""
    resp = requests.get(f"{BASE_URL}/collections/catalog", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, (
        f"Expected the 'catalog' collection to exist (HTTP 200), got "
        f"{resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("num_documents") == 6, (
        f"Expected 'catalog' to contain 6 documents, got {body.get('num_documents')}."
    )


def test_document_fields_p3(seeded):
    resp = requests.get(
        f"{BASE_URL}/collections/catalog/documents/P3", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Expected document P3 to exist, got {resp.status_code}: {resp.text}"
    )
    doc = resp.json()
    assert doc.get("badge") == "sponsored", (
        f"Expected P3.badge == 'sponsored', got {doc.get('badge')!r}."
    )
    assert int(doc.get("popularity")) == 5, (
        f"Expected P3.popularity == 5, got {doc.get('popularity')!r}."
    )
    assert doc.get("title") == "Alpine Trek Poles", (
        f"Expected P3.title == 'Alpine Trek Poles', got {doc.get('title')!r}."
    )


def test_document_fields_p6(seeded):
    resp = requests.get(
        f"{BASE_URL}/collections/catalog/documents/P6", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Expected document P6 to exist, got {resp.status_code}: {resp.text}"
    )
    doc = resp.json()
    assert doc.get("badge") == "featured", (
        f"Expected P6.badge == 'featured', got {doc.get('badge')!r}."
    )
    assert int(doc.get("popularity")) == 100, (
        f"Expected P6.popularity == 100, got {doc.get('popularity')!r}."
    )
    assert doc.get("title") == "Alpine Trek Socks", (
        f"Expected P6.title == 'Alpine Trek Socks', got {doc.get('title')!r}."
    )


def test_ranking_full_multi_signal(seeded):
    """Full ranking: eval tier dominates, then text relevance, then popularity."""
    order = _run_rank("alpine trek")
    assert order == ["P5", "P3", "P2", "P1", "P6", "P4"], (
        "Expected ranking ['P5','P3','P2','P1','P6','P4'] for query 'alpine trek'. "
        "This verifies the sponsored tier ranks first even though those items are the "
        "least text-relevant, that P2/P1 (matching in both fields) outrank P6 (title-only) "
        "despite P6 having the highest popularity, that P4 (highly relevant but untagged) "
        "is last, and that the popularity tiebreaker orders P5>P3 and P2>P1. "
        f"Got: {order}."
    )


def test_ranking_second_query(seeded):
    """A second query must yield a different, correctly ordered subset."""
    order = _run_rank("summit")
    assert order == ["P5", "P3"], (
        "Expected ranking ['P5','P3'] for query 'summit': only P3 and P5 match "
        "(both sponsored, equal relevance), so the higher-popularity P5 precedes P3. "
        f"Got: {order}."
    )
