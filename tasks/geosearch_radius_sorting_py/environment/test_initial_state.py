import json
import os

import pytest

PROJECT_DIR = "/home/user/project"
DATASET_PATH = os.path.join(PROJECT_DIR, "data", "airports.jsonl")
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"


def test_typesense_server_binary_available():
    assert os.path.isfile(TYPESENSE_BINARY) and os.access(TYPESENSE_BINARY, os.X_OK), (
        f"Typesense server binary not found or not executable at {TYPESENSE_BINARY}."
    )


def test_typesense_python_sdk_importable():
    try:
        import typesense  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"The 'typesense' Python SDK is not importable: {exc}")


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_dataset_file_exists():
    assert os.path.isfile(DATASET_PATH), f"Dataset file {DATASET_PATH} does not exist."


def test_dataset_is_valid_jsonl_with_required_fields():
    assert os.path.isfile(DATASET_PATH), f"Dataset file {DATASET_PATH} does not exist."
    lines = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for raw in f:
            if raw.strip():
                lines.append(raw)
    assert lines, f"Dataset file {DATASET_PATH} is empty."
    for i, raw in enumerate(lines, start=1):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Line {i} of {DATASET_PATH} is not valid JSON: {exc}")
        for key in ("id", "name", "iata", "lat", "lng"):
            assert key in record, (
                f"Record on line {i} of {DATASET_PATH} is missing required key '{key}'."
            )


def test_dataset_contains_edge_case_markers():
    ids = set()
    with open(DATASET_PATH, encoding="utf-8") as f:
        for raw in f:
            if raw.strip():
                ids.add(json.loads(raw)["id"])
    for marker in ("CDG", "EDGE_IN", "EDGE_OUT"):
        assert marker in ids, (
            f"Expected dataset {DATASET_PATH} to contain a record with id '{marker}'."
        )
