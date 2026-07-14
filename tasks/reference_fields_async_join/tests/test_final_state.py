import json
import os
import subprocess
import time

import pytest
import requests

HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
PROJECT_DIR = "/home/user/typesense-join"
DATA_DIR = "/home/user/typesense-join/typesense-data"
BINARY = "/usr/local/bin/typesense-server"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}
SERVER_LOG = "/tmp/typesense_verifier.log"


def _read_run_id():
    with open("/logs/artifacts/run-id") as f:
        return f.read().strip()


RUN_ID = _read_run_id()
USER_ID = f"zu{RUN_ID}"
PRODUCT_ID = f"zp{RUN_ID}"
USERNAME = f"zuser{RUN_ID}"
PRODUCT_NAME = f"zprod{RUN_ID}"
MISSING_PRODUCT_ID = f"no-such-product-{RUN_ID}"


def _health_ok():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=2)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except (requests.RequestException, ValueError):
        return False


@pytest.fixture(scope="session")
def typesense_server():
    """Ensure a Typesense server is running on port 8108 with the agent's data dir.

    If a server is already responding (e.g. the agent left it running), reuse it;
    otherwise start one against the persistent data directory so previously
    created collections are loaded.
    """
    proc = None
    if not _health_ok():
        os.makedirs(DATA_DIR, exist_ok=True)
        logf = open(SERVER_LOG, "w")
        proc = subprocess.Popen(
            [
                BINARY,
                f"--data-dir={DATA_DIR}",
                f"--api-key={API_KEY}",
                "--port",
                str(PORT),
                "--enable-cors",
            ],
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if _health_ok():
                break
            time.sleep(1)

    assert _health_ok(), (
        "Typesense server is not healthy on port 8108. It could not be reached "
        "and the verifier failed to start it against the persistent data dir."
    )
    yield
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            with open(SERVER_LOG) as f:
                print("===== Typesense server log (verifier-started) =====")
                print(f.read())
        except OSError:
            pass


def _get_collection(name):
    resp = requests.get(f"{BASE_URL}/collections/{name}", headers=HEADERS, timeout=10)
    return resp


def _find_field(schema, field_name):
    for field in schema.get("fields", []):
        if field.get("name") == field_name:
            return field
    return None


@pytest.fixture(scope="session")
def async_insert(typesense_server):
    """Perform the out-of-order async reference test against the running server.

    Insert a `likes` document that references a user and a product that do NOT
    exist yet, then index the referenced product and user afterwards, and wait
    for asynchronous reference resolution.
    """
    # 1. Insert the linking document BEFORE the referenced docs exist.
    like_resp = requests.post(
        f"{BASE_URL}/collections/likes/documents",
        headers=HEADERS,
        data=json.dumps({"user_id": USER_ID, "product_id": PRODUCT_ID}),
        timeout=15,
    )

    # 2. Now index the referenced product and user.
    prod_resp = requests.post(
        f"{BASE_URL}/collections/products/documents?action=upsert",
        headers=HEADERS,
        data=json.dumps({"id": PRODUCT_ID, "product_name": PRODUCT_NAME}),
        timeout=15,
    )
    user_resp = requests.post(
        f"{BASE_URL}/collections/users/documents?action=upsert",
        headers=HEADERS,
        data=json.dumps({"id": USER_ID, "username": USERNAME}),
        timeout=15,
    )

    # 3. Poll for asynchronous reference resolution (up to ~15s).
    resolved = False
    deadline = time.time() + 15
    while time.time() < deadline:
        search = requests.get(
            f"{BASE_URL}/collections/users/documents/search",
            headers=HEADERS,
            params={
                "q": "*",
                "query_by": "username",
                "filter_by": f"$likes(product_id:={PRODUCT_ID})",
            },
            timeout=10,
        )
        if search.status_code == 200 and search.json().get("found", 0) >= 1:
            resolved = True
            break
        time.sleep(1)

    return {
        "like_resp": like_resp,
        "prod_resp": prod_resp,
        "user_resp": user_resp,
        "resolved": resolved,
    }


def _run_query_cli(*args):
    result = subprocess.run(
        ["python3", "query.py", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
    )
    return result


def _parse_json_array(stdout):
    return json.loads(stdout.strip())


def test_collections_exist(typesense_server):
    resp = requests.get(f"{BASE_URL}/collections", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, (
        f"GET /collections failed with status {resp.status_code}: {resp.text}"
    )
    names = {c.get("name") for c in resp.json()}
    for expected in ("users", "products", "likes"):
        assert expected in names, (
            f"Expected collection '{expected}' to exist. Found collections: {names}"
        )


def test_likes_reference_fields_are_async(typesense_server):
    resp = _get_collection("likes")
    assert resp.status_code == 200, (
        f"GET /collections/likes failed with status {resp.status_code}: {resp.text}"
    )
    schema = resp.json()

    user_field = _find_field(schema, "user_id")
    assert user_field is not None, "Field 'user_id' not found in 'likes' collection."
    assert user_field.get("reference") == "users.id", (
        f"Field 'user_id' must reference 'users.id', got: {user_field.get('reference')}"
    )
    assert user_field.get("async_reference") is True, (
        "Field 'user_id' must have async_reference set to true, got: "
        f"{user_field.get('async_reference')}"
    )

    product_field = _find_field(schema, "product_id")
    assert product_field is not None, (
        "Field 'product_id' not found in 'likes' collection."
    )
    assert product_field.get("reference") == "products.id", (
        "Field 'product_id' must reference 'products.id', got: "
        f"{product_field.get('reference')}"
    )
    assert product_field.get("async_reference") is True, (
        "Field 'product_id' must have async_reference set to true, got: "
        f"{product_field.get('async_reference')}"
    )


def test_like_indexed_before_referenced_docs(async_insert):
    resp = async_insert["like_resp"]
    assert resp.status_code in (200, 201), (
        "Indexing a 'likes' document that references a not-yet-existing user and "
        f"product must succeed with async references. Got status {resp.status_code}: "
        f"{resp.text}"
    )
    # Typesense returns a JSON error body mentioning the missing reference when
    # async resolution is not enabled; ensure that did not happen.
    assert "not found in the collection" not in resp.text, (
        "The linking document was rejected because the referenced document was not "
        f"found; async_reference resolution is not working. Response: {resp.text}"
    )


def test_async_references_resolved(async_insert):
    assert async_insert["prod_resp"].status_code in (200, 201), (
        f"Failed to index referenced product: {async_insert['prod_resp'].text}"
    )
    assert async_insert["user_resp"].status_code in (200, 201), (
        f"Failed to index referenced user: {async_insert['user_resp'].text}"
    )
    assert async_insert["resolved"], (
        "The like's references did not resolve after the referenced user and "
        "product were indexed. A join search on 'users' filtered by "
        f"$likes(product_id:={PRODUCT_ID}) returned no results."
    )


def test_query_cli_product(async_insert):
    result = _run_query_cli("--product", PRODUCT_ID)
    assert result.returncode == 0, (
        f"`python3 query.py --product {PRODUCT_ID}` failed "
        f"(exit {result.returncode}). stderr: {result.stderr}"
    )
    try:
        value = _parse_json_array(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"stdout is not a valid JSON array: {exc}. stdout was: {result.stdout!r}"
        )
    assert value == [USERNAME], (
        f"Expected the usernames who liked product '{PRODUCT_ID}' to be "
        f"[{USERNAME!r}], got: {value!r}"
    )


def test_query_cli_user(async_insert):
    result = _run_query_cli("--user", USER_ID)
    assert result.returncode == 0, (
        f"`python3 query.py --user {USER_ID}` failed "
        f"(exit {result.returncode}). stderr: {result.stderr}"
    )
    try:
        value = _parse_json_array(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"stdout is not a valid JSON array: {exc}. stdout was: {result.stdout!r}"
        )
    assert value == [PRODUCT_NAME], (
        f"Expected the product names liked by user '{USER_ID}' to be "
        f"[{PRODUCT_NAME!r}], got: {value!r}"
    )


def test_query_cli_empty_result(async_insert):
    result = _run_query_cli("--product", MISSING_PRODUCT_ID)
    assert result.returncode == 0, (
        f"`python3 query.py --product {MISSING_PRODUCT_ID}` failed "
        f"(exit {result.returncode}). stderr: {result.stderr}"
    )
    try:
        value = _parse_json_array(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"stdout is not a valid JSON array: {exc}. stdout was: {result.stdout!r}"
        )
    assert value == [], (
        f"Expected an empty JSON array for a product with no likes, got: {value!r}"
    )


def test_server_side_join_resolves(async_insert):
    search = requests.get(
        f"{BASE_URL}/collections/users/documents/search",
        headers=HEADERS,
        params={
            "q": "*",
            "query_by": "username",
            "filter_by": f"$likes(product_id:={PRODUCT_ID})",
        },
        timeout=10,
    )
    assert search.status_code == 200, (
        f"Join search on 'users' failed with status {search.status_code}: {search.text}"
    )
    body = search.json()
    assert body.get("found", 0) == 1, (
        "Expected exactly one user linked to product "
        f"'{PRODUCT_ID}', got found={body.get('found')}. Response: {body}"
    )
    doc = body["hits"][0]["document"]
    assert doc.get("username") == USERNAME, (
        f"Expected joined user's username to be '{USERNAME}', got: {doc.get('username')}"
    )
