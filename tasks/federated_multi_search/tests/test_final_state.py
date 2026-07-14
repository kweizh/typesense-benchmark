import json
import os
import socket
import subprocess

import pytest
import requests
from xprocess import ProcessStarter

# Connect over IPv4 explicitly to avoid IPv6 loopback (::1) resolution surprises.
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

PROJECT_DIR = "/home/user/federated-search"
DATA_DIR = os.path.join(PROJECT_DIR, "typesense-data")
SERVER_BIN = "/usr/local/bin/typesense-server"

EXPECTED_COUNTS = {"products": 4, "articles": 3, "users": 3}


def _server_healthy():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def typesense_server(xprocess):
    """Ensure a Typesense server is reachable on 127.0.0.1:8108.

    If a server (e.g. one the executor started) is already healthy, reuse it to
    avoid a port conflict. Otherwise start the standalone binary via xprocess.
    """
    if _server_healthy():
        yield
        return

    os.makedirs(DATA_DIR, exist_ok=True)

    class Starter(ProcessStarter):
        name = "typesense_server"
        args = [
            SERVER_BIN,
            f"--data-dir={DATA_DIR}",
            f"--api-key={API_KEY}",
            f"--port={PORT}",
            "--enable-cors",
        ]
        env = os.environ.copy()
        popen_kwargs = {"cwd": PROJECT_DIR, "text": True}
        timeout = 120
        terminate_on_interrupt = True

        def startup_check(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((HOST, PORT)) != 0:
                    return False
            return _server_healthy()

    info = xprocess.getinfo(Starter.name)
    started = False
    try:
        xprocess.ensure(Starter.name, Starter)
        started = True
    finally:
        try:
            with open(info.logpath, "r") as f:
                print(f"===== typesense-server log ({'STARTED' if started else 'FAILED'}) =====")
                print(f.read())
        except OSError:
            pass

    yield

    info.terminate()


def _run_setup():
    result = subprocess.run(
        ["python3", "setup.py"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result


@pytest.fixture(scope="session")
def provisioned(typesense_server):
    """Run the executor's idempotent provisioning command once for the session."""
    result = _run_setup()
    assert result.returncode == 0, (
        f"`python3 setup.py` failed (exit {result.returncode}).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    yield


def _run_search(query):
    result = subprocess.run(
        ["python3", "search.py", "--query", query],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


def _parse_search_output(result, query):
    assert result.returncode == 0, (
        f"`python3 search.py --query {query!r}` exited with {result.returncode} "
        f"(expected 0).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"search.py did not print a single valid JSON object to stdout for "
            f"query {query!r}: {exc}\nstdout was:\n{result.stdout}"
        )
    assert isinstance(payload, dict), f"Expected a JSON object, got {type(payload)}."
    assert "results" in payload and isinstance(payload["results"], dict), (
        f"Expected a top-level 'results' object in the output, got keys: {list(payload)}"
    )
    results = payload["results"]
    assert set(results.keys()) == {"products", "articles", "users"}, (
        f"'results' must contain exactly the keys products, articles, users; "
        f"got: {sorted(results.keys())}"
    )
    return results


def _hit_ids(section, collection):
    assert "hits" in section and isinstance(section["hits"], list), (
        f"Section '{collection}' must contain a 'hits' list; got: {section}"
    )
    ids = []
    for hit in section["hits"]:
        assert isinstance(hit, dict) and "id" in hit, (
            f"Each hit in '{collection}' must be a document object with an 'id'; got: {hit}"
        )
        ids.append(hit["id"])
    return set(ids)


def test_setup_populates_collections(provisioned):
    """Truth Setup: each collection exists and is fully populated."""
    for collection, expected in EXPECTED_COUNTS.items():
        resp = requests.get(f"{BASE_URL}/collections/{collection}", headers=HEADERS, timeout=10)
        assert resp.status_code == 200, (
            f"Collection '{collection}' was not found via the Typesense API "
            f"(status {resp.status_code}): {resp.text}"
        )
        num_docs = resp.json().get("num_documents")
        assert num_docs == expected, (
            f"Collection '{collection}' should contain {expected} documents, got {num_docs}."
        )


def test_federated_search_across_collections(provisioned):
    """Truth step 1: federated grouped search across all three collections."""
    results = _parse_search_output(_run_search("wireless"), "wireless")

    products = results["products"]
    assert products.get("found") == 2, f"products.found should be 2, got: {products.get('found')}"
    assert _hit_ids(products, "products") == {"p1", "p4"}, (
        f"products hits should be {{p1, p4}}, got: {_hit_ids(products, 'products')}"
    )

    articles = results["articles"]
    assert articles.get("found") == 1, f"articles.found should be 1, got: {articles.get('found')}"
    assert _hit_ids(articles, "articles") == {"a1"}, (
        f"articles hits should be {{a1}}, got: {_hit_ids(articles, 'articles')}"
    )

    users = results["users"]
    assert users.get("found") == 1, f"users.found should be 1, got: {users.get('found')}"
    assert _hit_ids(users, "users") == {"u1"}, (
        f"users hits should be {{u1}}, got: {_hit_ids(users, 'users')}"
    )


def test_per_collection_query_fields(provisioned):
    """Truth step 2: each collection is searched using its own fields only."""
    results = _parse_search_output(_run_search("jane"), "jane")

    products = results["products"]
    assert products.get("found") == 0, f"products.found should be 0 for 'jane', got: {products.get('found')}"
    assert _hit_ids(products, "products") == set(), "products should have no hits for 'jane'."

    articles = results["articles"]
    assert articles.get("found") == 0, (
        "articles.found should be 0 for 'jane' ('jane' only appears in the non-searched "
        f"author field), got: {articles.get('found')}"
    )
    assert _hit_ids(articles, "articles") == set(), "articles should have no hits for 'jane'."

    users = results["users"]
    assert users.get("found") == 1, f"users.found should be 1 for 'jane', got: {users.get('found')}"
    assert _hit_ids(users, "users") == {"u3"}, (
        f"users hits should be {{u3}} (matched via full_name 'Jane Doe'), "
        f"got: {_hit_ids(users, 'users')}"
    )


def test_uses_multi_search_endpoint(provisioned):
    """Truth step 4: the project issues a single federated multi_search request."""
    matches = subprocess.run(
        ["grep", "-R", "multi_search", PROJECT_DIR, "--include=*.py"],
        capture_output=True,
        text=True,
    )
    assert matches.returncode == 0 and matches.stdout.strip(), (
        "Expected the project's Python source to use the federated 'multi_search' "
        f"endpoint / SDK call, but no reference was found.\nstdout:\n{matches.stdout}\n"
        f"stderr:\n{matches.stderr}"
    )


def test_partial_failure_handling(provisioned):
    """Truth step 3: a failing sub-query must not crash the command; other
    collections still return results and the failing one carries an error."""
    # Force one sub-query to fail by dropping the users collection.
    del_resp = requests.delete(f"{BASE_URL}/collections/users", headers=HEADERS, timeout=10)
    assert del_resp.status_code in (200, 404), (
        f"Failed to drop 'users' collection to simulate a partial failure: "
        f"{del_resp.status_code} {del_resp.text}"
    )

    try:
        results = _parse_search_output(_run_search("wireless"), "wireless")

        # Successful collections are unaffected.
        products = results["products"]
        assert products.get("found") == 2 and _hit_ids(products, "products") == {"p1", "p4"}, (
            f"products should still return hits {{p1, p4}} despite the users failure; got: {products}"
        )
        articles = results["articles"]
        assert articles.get("found") == 1 and _hit_ids(articles, "articles") == {"a1"}, (
            f"articles should still return hit {{a1}} despite the users failure; got: {articles}"
        )

        # The failing collection carries an error and no hits.
        users = results["users"]
        assert "error" in users and isinstance(users["error"], str) and users["error"], (
            f"users section should contain a non-empty 'error' string after its sub-query "
            f"failed; got: {users}"
        )
        assert "hits" not in users, (
            f"users section must not contain a 'hits' array when its sub-query failed; got: {users}"
        )
    finally:
        # Restore the dropped collection for a clean post-verification state.
        restore = _run_setup()
        assert restore.returncode == 0, (
            f"Failed to restore state via `python3 setup.py` after the partial-failure test.\n"
            f"stdout:\n{restore.stdout}\nstderr:\n{restore.stderr}"
        )
