import json
import os
import shutil
import socket
import subprocess
import time

import pytest
import requests
from xprocess import ProcessStarter

PROJECT_DIR = "/home/user/project"
DATASET_PATH = os.path.join(PROJECT_DIR, "data", "airports.jsonl")
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"
DATA_DIR = os.path.join(PROJECT_DIR, "typesense-data")

API_KEY = "xyz"
# Connect over IPv4 explicitly to avoid IPv6 loopback resolution issues.
HOST = "127.0.0.1"
PORT = 8108
BASE_URL = f"http://{HOST}:{PORT}"

CDG_LAT = 49.0097
CDG_LNG = 2.5479


def _count_dataset_records():
    count = 0
    with open(DATASET_PATH, encoding="utf-8") as f:
        for raw in f:
            if raw.strip():
                count += 1
    return count


def _direct_search(lat, lng, radius_km):
    """Ground-truth query issued directly against Typesense's HTTP API."""
    params = {
        "q": "*",
        "query_by": "name",
        "filter_by": f"location:({lat}, {lng}, {radius_km} km)",
        "sort_by": f"location({lat}, {lng}):asc",
        "per_page": 250,
    }
    resp = requests.get(
        f"{BASE_URL}/collections/airports/documents/search",
        params=params,
        headers={"X-TYPESENSE-API-KEY": API_KEY},
        timeout=30,
    )
    assert resp.status_code == 200, (
        f"Direct Typesense search failed ({resp.status_code}): {resp.text}"
    )
    data = resp.json()
    hits = data.get("hits", [])
    ordered = []
    for hit in hits:
        doc = hit["document"]
        dist = hit["geo_distance_meters"]["location"]
        ordered.append((doc["id"], int(dist)))
    return data.get("found", 0), ordered


def _run_cli(lat, lng, radius_km):
    result = subprocess.run(
        [
            "python3",
            "search.py",
            "--lat",
            str(lat),
            "--lng",
            str(lng),
            "--radius-km",
            str(radius_km),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, (
        f"search.py exited with {result.returncode}. stderr: {result.stderr}"
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"search.py did not print valid JSON. stdout: {result.stdout!r} ({exc})")
    return payload


@pytest.fixture(scope="session")
def typesense_index(xprocess):
    """Start a fresh Typesense server and rebuild the index via the executor's script."""
    # Ensure a clean, deterministic starting state.
    subprocess.run(["pkill", "-f", "typesense-server"], capture_output=True, text=True)
    time.sleep(1)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    class Starter(ProcessStarter):
        name = "typesense_server"
        args = [
            TYPESENSE_BINARY,
            f"--data-dir={DATA_DIR}",
            f"--api-key={API_KEY}",
            f"--port={PORT}",
            "--enable-cors",
        ]
        env = os.environ.copy()
        popen_kwargs = {"cwd": PROJECT_DIR, "text": True}
        timeout = 60
        terminate_on_interrupt = True

        def startup_check(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((HOST, PORT)) != 0:
                    return False
            try:
                resp = requests.get(f"{BASE_URL}/health", timeout=10)
                return resp.status_code == 200 and resp.json().get("ok") is True
            except requests.RequestException:
                return False

    info = xprocess.getinfo(Starter.name)

    def capture_logs(tag):
        try:
            with open(info.logpath, "r") as f:
                content = f.read()
        except OSError:
            content = "(no log file)"
        print(f"===== [{tag}] typesense_server log =====")
        print(content)
        print(f"===== [{tag}] end typesense_server log =====")

    started = False
    try:
        xprocess.ensure(Starter.name, Starter)
        started = True
    finally:
        capture_logs("STARTED" if started else "FAILED")

    # Rebuild the index using the executor's own build script.
    build = subprocess.run(
        ["python3", "build_index.py"],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    print(f"build_index.py stdout: {build.stdout}")
    print(f"build_index.py stderr: {build.stderr}")
    assert build.returncode == 0, (
        f"build_index.py failed with {build.returncode}: {build.stderr}"
    )

    yield

    capture_logs("TEARDOWN")
    info.terminate()


def test_collection_schema(typesense_index):
    resp = requests.get(
        f"{BASE_URL}/collections/airports",
        headers={"X-TYPESENSE-API-KEY": API_KEY},
        timeout=30,
    )
    assert resp.status_code == 200, (
        f"Collection 'airports' not retrievable ({resp.status_code}): {resp.text}"
    )
    schema = resp.json()
    expected_n = _count_dataset_records()
    assert schema.get("num_documents") == expected_n, (
        f"Expected {expected_n} documents in 'airports', got {schema.get('num_documents')}."
    )
    location_fields = [
        f for f in schema.get("fields", []) if f.get("name") == "location"
    ]
    assert location_fields, "Collection 'airports' has no field named 'location'."
    assert location_fields[0].get("type") == "geopoint", (
        f"Field 'location' must be of type 'geopoint', got {location_fields[0].get('type')}."
    )


def test_broad_radius_100km(typesense_index):
    payload = _run_cli(CDG_LAT, CDG_LNG, 100)
    gt_found, gt_ordered = _direct_search(CDG_LAT, CDG_LNG, 100)

    ref = payload.get("reference", {})
    assert float(ref.get("lat")) == CDG_LAT, f"reference.lat wrong: {ref}"
    assert float(ref.get("lng")) == CDG_LNG, f"reference.lng wrong: {ref}"
    assert float(ref.get("radius_km")) == 100.0, f"reference.radius_km wrong: {ref}"

    results = payload.get("results")
    assert isinstance(results, list), "results must be a list."
    assert payload.get("found") == gt_found, (
        f"found={payload.get('found')} but ground truth expects {gt_found}."
    )
    assert payload.get("found") == len(results), (
        f"found ({payload.get('found')}) must equal len(results) ({len(results)})."
    )

    cli_ids = [r["id"] for r in results]
    gt_ids = [i for i, _ in gt_ordered]
    assert cli_ids == gt_ids, (
        f"Ordered ids mismatch. CLI={cli_ids} ground_truth={gt_ids}."
    )

    gt_dist = {i: d for i, d in gt_ordered}
    for r in results:
        assert int(r["distance_meters"]) == gt_dist[r["id"]], (
            f"distance_meters mismatch for {r['id']}: CLI={r['distance_meters']} "
            f"ground_truth={gt_dist[r['id']]}."
        )
        assert set(r.keys()) == {"id", "iata", "name", "distance_meters"}, (
            f"Hit object has wrong keys: {sorted(r.keys())}."
        )

    dists = [int(r["distance_meters"]) for r in results]
    assert dists == sorted(dists), f"results not sorted by ascending distance: {dists}."
    assert results, "Expected at least one airport within 100 km of CDG."
    assert results[0]["id"] == "CDG", f"Nearest airport should be CDG, got {results[0]['id']}."
    assert int(results[0]["distance_meters"]) == 0, (
        f"CDG distance should be 0, got {results[0]['distance_meters']}."
    )

    for outside in ("LHR", "FRA", "AMS", "BRU"):
        assert outside not in cli_ids, (
            f"{outside} is beyond 100 km and must not appear in results: {cli_ids}."
        )


def test_coordinate_order_not_swapped(typesense_index):
    payload = _run_cli(CDG_LAT, CDG_LNG, 100)
    cli_ids = [r["id"] for r in payload.get("results", [])]

    _, correct_ordered = _direct_search(CDG_LAT, CDG_LNG, 100)
    correct_ids = [i for i, _ in correct_ordered]
    _, swapped_ordered = _direct_search(CDG_LNG, CDG_LAT, 100)
    swapped_ids = [i for i, _ in swapped_ordered]

    assert cli_ids == correct_ids, (
        "CLI results do not match correct [lat, lng] ordering ground truth."
    )
    assert cli_ids != swapped_ids, (
        "CLI results match the swapped [lng, lat] ordering, indicating wrong coordinate order."
    )


def test_exact_radius_edge_case(typesense_index):
    payload = _run_cli(CDG_LAT, CDG_LNG, 100)
    cli_ids = set(r["id"] for r in payload.get("results", []))

    _, gt_ordered = _direct_search(CDG_LAT, CDG_LNG, 100)
    gt_ids = set(i for i, _ in gt_ordered)

    for marker in ("EDGE_IN", "EDGE_OUT"):
        assert (marker in cli_ids) == (marker in gt_ids), (
            f"Membership of edge marker {marker} disagrees with Typesense ground truth. "
            f"CLI has it: {marker in cli_ids}, ground truth has it: {marker in gt_ids}."
        )


def test_tight_radius_10km(typesense_index):
    payload = _run_cli(CDG_LAT, CDG_LNG, 10)
    gt_found, gt_ordered = _direct_search(CDG_LAT, CDG_LNG, 10)
    gt_ids = [i for i, _ in gt_ordered]
    cli_ids = [r["id"] for r in payload.get("results", [])]

    assert payload.get("found") == gt_found, (
        f"found={payload.get('found')} but ground truth expects {gt_found} at 10 km."
    )
    assert cli_ids == gt_ids, (
        f"Ordered ids mismatch at 10 km. CLI={cli_ids} ground_truth={gt_ids}."
    )
    assert "CDG" in cli_ids, "CDG should be within 10 km of itself."
    assert "LBG" in cli_ids, "LBG (~9 km) should be within 10 km of CDG."
    assert "ORY" not in cli_ids, "ORY (~35 km) must not be within 10 km of CDG."


def test_empty_result_mid_atlantic(typesense_index):
    payload = _run_cli(30.0, -40.0, 50)
    assert payload.get("found") == 0, (
        f"Expected 0 airports near mid-Atlantic point, got {payload.get('found')}."
    )
    assert payload.get("results") == [], (
        f"Expected empty results near mid-Atlantic point, got {payload.get('results')}."
    )
