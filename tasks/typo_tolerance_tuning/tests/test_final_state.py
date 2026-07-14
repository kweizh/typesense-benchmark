import json
import os
import re
import socket
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/typo-tuning"
DATA_DIR = "/home/user/typo-tuning/ts-data"
BINARY_PATH = "/usr/local/bin/typesense-server"
API_KEY = "xyz"
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

# (case name, query string, expected set of matching document ids)
QUERY_CASES = [
    ("brand_exact", "Keychron", {"2"}),
    ("brand_no_typo", "keichron", set()),
    ("name_two_typo_six_letters", "carema", {"3"}),
    ("four_letter_token_corrected", "wiff", {"9"}),
    ("three_letter_token_not_corrected", "usq", set()),
    ("drop_tokens_partial", "Anker Speaker", {"5", "6"}),
    ("drop_tokens_not_overreaching", "Camera Bag", {"3"}),
    ("split_join_join", "basket ball", {"7"}),
    ("split_join_split", "waterbottle", {"8"}),
    ("no_excess_typo_search", "charger", {"6"}),
]


def _is_healthy():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except (requests.RequestException, ValueError):
        return False


@pytest.fixture(scope="session")
def typesense_server():
    """Ensure a Typesense server is reachable on 127.0.0.1:8108.

    If the agent's server is already running, reuse it. Otherwise start one
    against the known data directory (documents persist on disk and are
    reloaded on restart).
    """
    started_proc = None
    if not _is_healthy():
        os.makedirs(DATA_DIR, exist_ok=True)
        started_proc = subprocess.Popen(
            [
                BINARY_PATH,
                f"--data-dir={DATA_DIR}",
                f"--api-key={API_KEY}",
                f"--port={PORT}",
                "--enable-cors",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            # Fail fast if the process exited early.
            if started_proc.poll() is not None:
                out = started_proc.stdout.read() if started_proc.stdout else ""
                raise RuntimeError(
                    f"typesense-server exited early with code "
                    f"{started_proc.returncode}. Logs:\n{out}"
                )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((HOST, PORT)) == 0 and _is_healthy():
                    break
            time.sleep(1)

    assert _is_healthy(), (
        f"Typesense server is not healthy at {BASE_URL}/health. It must be "
        "running for verification."
    )

    yield

    if started_proc is not None:
        started_proc.terminate()
        try:
            started_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            started_proc.kill()


def _run_search(query):
    result = subprocess.run(
        ["python3", "search.py", "--q", query],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"`python3 search.py --q {query!r}` exited with code "
        f"{result.returncode}. stderr:\n{result.stderr}"
    )
    stdout = result.stdout.strip()
    parsed = None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        # Be lenient: extract the first JSON array present in stdout.
        match = re.search(r"\[.*\]", stdout, re.DOTALL)
        assert match is not None, (
            f"search.py did not print a JSON array for query {query!r}. "
            f"stdout was:\n{stdout}"
        )
        parsed = json.loads(match.group(0))
    assert isinstance(parsed, list), (
        f"search.py output for query {query!r} must be a JSON array, got "
        f"{type(parsed).__name__}: {stdout}"
    )
    return {str(item) for item in parsed}


def test_search_script_exists():
    path = os.path.join(PROJECT_DIR, "search.py")
    assert os.path.isfile(path), f"Expected search tool at {path}."


def test_catalog_collection_populated(typesense_server):
    resp = requests.get(
        f"{BASE_URL}/collections/catalog", headers=HEADERS, timeout=10
    )
    assert resp.status_code == 200, (
        f"Could not retrieve the 'catalog' collection (status "
        f"{resp.status_code}): {resp.text}"
    )
    info = resp.json()
    assert info.get("name") == "catalog", (
        f"Expected a collection named 'catalog', got {info.get('name')!r}."
    )
    assert info.get("num_documents") == 11, (
        f"Expected 11 documents in 'catalog', got "
        f"{info.get('num_documents')}."
    )
    field_names = {f.get("name") for f in info.get("fields", [])}
    assert "name" in field_names, "Collection 'catalog' must have a 'name' field."
    assert "brand" in field_names, (
        "Collection 'catalog' must have a 'brand' field."
    )


@pytest.mark.parametrize(
    "case_name,query,expected",
    QUERY_CASES,
    ids=[c[0] for c in QUERY_CASES],
)
def test_typo_tolerance_behavior(typesense_server, case_name, query, expected):
    actual = _run_search(query)
    assert actual == expected, (
        f"[{case_name}] query {query!r} returned ids {sorted(actual)}, "
        f"expected {sorted(expected)}."
    )
