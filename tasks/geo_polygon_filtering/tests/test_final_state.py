import json
import os
import re
import subprocess
import time

import pytest
import requests

PROJECT_DIR = "/home/user/geo-search"
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"
API_KEY = os.environ.get("TYPESENSE_API_KEY", "xyz")
HEADERS = {"X-TYPESENSE-API-KEY": API_KEY}

START_SCRIPT = os.path.join(PROJECT_DIR, "start.sh")
SEED_SCRIPT = os.path.join(PROJECT_DIR, "seed.py")
SEARCH_SCRIPT = os.path.join(PROJECT_DIR, "search.py")

# Polygon fixtures used by the verification plan.
TRIANGLE = "37.80,-122.45,37.80,-122.39,37.74,-122.42"
BBOX = "37.773,-122.425,37.773,-122.415,37.782,-122.415,37.782,-122.425"


def _wait_for_health(timeout=120):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=5)
            if resp.status_code == 200 and resp.json().get("ok") is True:
                return True
        except requests.RequestException as exc:  # pragma: no cover - retry loop
            last_err = exc
        time.sleep(1)
    raise AssertionError(
        f"Typesense server did not become healthy at {BASE_URL}/health within "
        f"{timeout}s. Last error: {last_err}"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_typesense():
    """Start the Typesense server and seed the dataset before verification."""
    assert os.path.isfile(START_SCRIPT), f"Start script missing at {START_SCRIPT}."
    start = subprocess.run(
        ["bash", START_SCRIPT],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=180,
    )
    print("=== start.sh stdout ===\n" + start.stdout)
    print("=== start.sh stderr ===\n" + start.stderr)

    _wait_for_health()

    assert os.path.isfile(SEED_SCRIPT), f"Seed script missing at {SEED_SCRIPT}."
    seed = subprocess.run(
        ["python3", SEED_SCRIPT],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=120,
    )
    print("=== seed.py stdout ===\n" + seed.stdout)
    print("=== seed.py stderr ===\n" + seed.stderr)
    assert seed.returncode == 0, f"Seeding failed (exit {seed.returncode}): {seed.stderr}"
    yield


def _run_search(polygon, exclude_status=None):
    cmd = ["python3", SEARCH_SCRIPT, "--polygon", polygon]
    if exclude_status is not None:
        cmd += ["--exclude-status", exclude_status]
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=PROJECT_DIR, timeout=60
    )
    print(f"=== search cmd: {cmd} ===")
    print("=== search stdout ===\n" + result.stdout)
    print("=== search stderr ===\n" + result.stderr)
    assert result.returncode == 0, (
        f"search.py exited with {result.returncode}: {result.stderr}"
    )
    match = re.search(r'\{[^{}]*"hub_ids"[^{}]*\}', result.stdout)
    assert match is not None, (
        f"Could not find a JSON object with key 'hub_ids' in stdout:\n{result.stdout}"
    )
    payload = json.loads(match.group(0))
    assert list(payload.keys()) == ["hub_ids"], (
        f"Output JSON must contain exactly the key 'hub_ids', got: {payload}"
    )
    ids = payload["hub_ids"]
    assert isinstance(ids, list), f"'hub_ids' must be a list, got: {ids!r}"
    return ids


def test_collection_exists_and_seeded():
    resp = requests.get(f"{BASE_URL}/collections/hubs", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, (
        f"Expected collection 'hubs' to exist (status {resp.status_code}): {resp.text}"
    )
    data = resp.json()
    assert data.get("num_documents") == 10, (
        f"Expected 10 seeded documents in 'hubs', got: {data.get('num_documents')}"
    )
    fields = {f["name"]: f["type"] for f in data.get("fields", [])}
    assert fields.get("location") == "geopoint", (
        f"Expected a 'location' field of type 'geopoint', got fields: {fields}"
    )


def test_polygon_with_exclusion_main_case():
    ids = _run_search(TRIANGLE, exclude_status="maintenance")
    assert sorted(ids) == ["h01", "h02", "h07"], (
        "Polygon+exclusion should return only inside-and-active hubs "
        f"['h01','h02','h07'], got: {ids}"
    )


def test_polygon_without_exclusion():
    ids = _run_search(TRIANGLE)
    assert sorted(ids) == ["h01", "h02", "h07", "h09", "h10"], (
        "Polygon without exclusion should return all hubs inside the triangle "
        f"['h01','h02','h07','h09','h10'], got: {ids}"
    )


def test_bounding_box_polygon_with_exclusion():
    ids = _run_search(BBOX, exclude_status="maintenance")
    assert sorted(ids) == ["h01"], (
        "Bounding-box polygon+exclusion should return only ['h01'] "
        f"(h09 excluded by status, h10 outside the box), got: {ids}"
    )


def test_edge_discrimination_inside_vs_outside():
    ids = _run_search(TRIANGLE)
    assert "h07" in ids, (
        "h07 lies just inside the polygon's left edge and must be included, "
        f"got: {ids}"
    )
    assert "h08" not in ids, (
        "h08 lies just outside the polygon's left edge and must NOT be included; "
        f"this confirms true polygon containment rather than a radius approximation. Got: {ids}"
    )
