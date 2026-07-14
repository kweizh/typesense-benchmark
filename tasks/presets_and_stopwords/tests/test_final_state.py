import json
import os
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/typesense-app"
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}


def _health_ok(timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=3)
            if resp.status_code == 200 and resp.json().get("ok") is True:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def _run_setup():
    """Run the agent's idempotent setup command and return the CompletedProcess."""
    return subprocess.run(
        ["python3", "run.py", "--setup"],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=180,
    )


@pytest.fixture(scope="session")
def typesense_env(tmp_path_factory):
    """Ensure a Typesense server is running and the task resources are set up.

    If the agent already left a server running on port 8108 we reuse it;
    otherwise we start one ourselves so the API checks can proceed.
    """
    started_proc = None
    if not _health_ok(3):
        data_dir = tmp_path_factory.mktemp("typesense-data")
        started_proc = subprocess.Popen(
            [
                TYPESENSE_BINARY,
                f"--data-dir={data_dir}",
                f"--api-key={API_KEY}",
                f"--port={PORT}",
                "--enable-cors",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert _health_ok(30), "Typesense server did not become healthy within 30s."

    # Ensure the collection, documents, stopwords set and preset exist.
    result = _run_setup()
    print("=== run.py --setup stdout ===")
    print(result.stdout)
    print("=== run.py --setup stderr ===")
    print(result.stderr)
    assert result.returncode == 0, (
        f"'python3 run.py --setup' failed with code {result.returncode}: {result.stderr}"
    )
    assert _health_ok(30), "Typesense server is not healthy after running setup."

    yield

    if started_proc is not None:
        started_proc.terminate()
        try:
            started_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            started_proc.kill()


def _run_search(query: str, explicit: bool = False) -> dict:
    args = ["python3", "run.py", "--q", query]
    if explicit:
        args.append("--explicit")
    result = subprocess.run(
        args, capture_output=True, text=True, cwd=PROJECT_DIR, timeout=90
    )
    assert result.returncode == 0, (
        f"Search command {args} failed (code {result.returncode}): {result.stderr}"
    )
    return _parse_json_output(result.stdout, args)


def _parse_json_output(stdout: str, args) -> dict:
    stdout = stdout.strip()
    # Prefer parsing the whole output; fall back to the last JSON-looking line.
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    raise AssertionError(
        f"Command {args} did not print a single JSON object. Got:\n{stdout}"
    )


def _extract_stopwords_list(payload: dict):
    sw = payload.get("stopwords")
    if isinstance(sw, dict):
        sw = sw.get("stopwords")
    return sw


def _extract_preset_value(payload: dict):
    value = payload.get("value")
    if isinstance(value, str):
        value = json.loads(value)
    return value


def test_setup_is_idempotent(typesense_env):
    """Re-running setup must succeed even though everything already exists."""
    result = _run_setup()
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, (
        f"Re-running 'python3 run.py --setup' failed (not idempotent): {result.stderr}"
    )


def test_health_ok(typesense_env):
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code == 200, f"Health endpoint returned {resp.status_code}."
    assert resp.json().get("ok") is True, f"Health payload not ok: {resp.text}"


def test_collection_exists_and_populated(typesense_env):
    resp = requests.get(f"{BASE_URL}/collections/library", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, (
        f"Collection 'library' not found (status {resp.status_code}): {resp.text}"
    )
    data = resp.json()
    assert data.get("num_documents") == 5, (
        f"Expected 5 documents in 'library', got {data.get('num_documents')}."
    )
    assert data.get("default_sorting_field") == "points", (
        f"Expected default_sorting_field 'points', got {data.get('default_sorting_field')}."
    )
    field_types = {f["name"]: f["type"] for f in data.get("fields", [])}
    assert field_types.get("title") == "string", (
        f"Field 'title' should be string, got {field_types.get('title')}."
    )
    assert field_types.get("author") == "string", (
        f"Field 'author' should be string, got {field_types.get('author')}."
    )
    assert field_types.get("points") == "int32", (
        f"Field 'points' should be int32, got {field_types.get('points')}."
    )


def test_stopwords_set_created(typesense_env):
    resp = requests.get(
        f"{BASE_URL}/stopwords/en_stopwords", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Stopwords set 'en_stopwords' not found (status {resp.status_code}): {resp.text}"
    )
    stopwords = _extract_stopwords_list(resp.json())
    assert isinstance(stopwords, list), (
        f"Could not read a stopwords list from response: {resp.text}"
    )
    normalized = {str(w).lower() for w in stopwords}
    assert normalized == {"the", "a", "of", "and"}, (
        f"Expected stopwords {{the, a, of, and}} (case-insensitive), got {normalized}."
    )


def test_preset_created_with_expected_parameters(typesense_env):
    resp = requests.get(
        f"{BASE_URL}/presets/library_default", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Preset 'library_default' not found (status {resp.status_code}): {resp.text}"
    )
    value = _extract_preset_value(resp.json())
    assert isinstance(value, dict), (
        f"Preset value should be a flat object of search parameters, got: {resp.text}"
    )
    assert value.get("query_by") == "title,author", (
        f"Preset query_by should be 'title,author', got {value.get('query_by')!r}."
    )
    assert value.get("sort_by") == "points:desc", (
        f"Preset sort_by should be 'points:desc', got {value.get('sort_by')!r}."
    )
    assert value.get("stopwords") == "en_stopwords", (
        f"Preset should apply the 'en_stopwords' stopwords set, got {value.get('stopwords')!r}."
    )


def test_preset_search_returns_points_sorted_results(typesense_env):
    result = _run_search("wizard")
    assert result == {"found": 2, "hits": ["3", "2"]}, (
        f"Expected wizard search to return the two wizard books sorted by points "
        f"(desc) as {{'found': 2, 'hits': ['3', '2']}}, got {result}."
    )


def test_stopwords_are_ignored_during_query(typesense_env):
    with_stopword = _run_search("the wizard")
    without_stopword = _run_search("wizard")
    assert with_stopword == {"found": 2, "hits": ["3", "2"]}, (
        f"'the wizard' should drop the stopword 'the' and match the same two wizard "
        f"books as 'wizard': expected {{'found': 2, 'hits': ['3', '2']}}, got {with_stopword}."
    )
    assert with_stopword == without_stopword, (
        f"Stopword 'the' was not ignored: 'the wizard' -> {with_stopword} "
        f"differs from 'wizard' -> {without_stopword}."
    )


def test_preset_matches_explicit_parameters(typesense_env):
    preset_wizard = _run_search("the wizard")
    explicit_wizard = _run_search("the wizard", explicit=True)
    assert preset_wizard == explicit_wizard, (
        f"Preset-driven search {preset_wizard} differs from explicit-parameter "
        f"search {explicit_wizard} for query 'the wizard'."
    )
    assert explicit_wizard == {"found": 2, "hits": ["3", "2"]}, (
        f"Explicit search for 'the wizard' should be {{'found': 2, 'hits': ['3', '2']}}, "
        f"got {explicit_wizard}."
    )

    preset_harry = _run_search("harry potter")
    explicit_harry = _run_search("harry potter", explicit=True)
    assert preset_harry == explicit_harry, (
        f"Preset-driven search {preset_harry} differs from explicit-parameter "
        f"search {explicit_harry} for query 'harry potter'."
    )
    assert explicit_harry == {"found": 1, "hits": ["4"]}, (
        f"Search for 'harry potter' should be {{'found': 1, 'hits': ['4']}}, "
        f"got {explicit_harry}."
    )


def test_single_token_search(typesense_env):
    result = _run_search("gatsby")
    assert result == {"found": 1, "hits": ["1"]}, (
        f"Search for 'gatsby' should be {{'found': 1, 'hits': ['1']}}, got {result}."
    )
