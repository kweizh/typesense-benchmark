import json
import os

import pytest

PROJECT_DIR = "/home/user/facet-nav"
DATA_FILE = os.path.join(PROJECT_DIR, "data", "products.jsonl")
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"

REQUIRED_FIELDS = ("product_name", "brand", "category", "tags", "price", "rating")


def test_typesense_server_binary_available():
    assert os.path.isfile(TYPESENSE_BINARY), (
        f"Typesense server binary not found at {TYPESENSE_BINARY}."
    )
    assert os.access(TYPESENSE_BINARY, os.X_OK), (
        f"Typesense server binary at {TYPESENSE_BINARY} is not executable."
    )


def test_typesense_python_sdk_importable():
    try:
        import typesense  # noqa: F401
    except ImportError as exc:  # pragma: no cover - failure path
        pytest.fail(f"The 'typesense' Python SDK is not importable: {exc}")


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_dataset_file_exists():
    assert os.path.isfile(DATA_FILE), (
        f"Product dataset file {DATA_FILE} does not exist."
    )


def test_dataset_has_twelve_products():
    with open(DATA_FILE, encoding="utf-8") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    assert len(lines) == 12, (
        f"Expected 12 products in {DATA_FILE}, found {len(lines)}."
    )


def test_dataset_records_are_well_formed():
    with open(DATA_FILE, encoding="utf-8") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    for idx, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Line {idx} of {DATA_FILE} is not valid JSON: {exc}")
        for field in REQUIRED_FIELDS:
            assert field in record, (
                f"Record on line {idx} is missing required field '{field}'."
            )
        assert isinstance(record["tags"], list), (
            f"Record on line {idx} field 'tags' must be a list."
        )
