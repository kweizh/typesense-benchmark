import json
import os

import pytest

PROJECT_DIR = "/home/user/nested-search"
DATA_FILE = os.path.join(PROJECT_DIR, "data", "orders.jsonl")
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"


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
    except ImportError as exc:  # pragma: no cover
        pytest.fail(f"The 'typesense' Python SDK could not be imported: {exc}")


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_dataset_file_exists():
    assert os.path.isfile(DATA_FILE), (
        f"Dataset file {DATA_FILE} does not exist."
    )


def test_dataset_has_four_customer_documents():
    with open(DATA_FILE) as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    assert len(lines) == 4, (
        f"Expected 4 customer documents in {DATA_FILE}, found {len(lines)}."
    )
    for line in lines:
        doc = json.loads(line)
        assert "id" in doc and "orders" in doc, (
            "Each dataset document must contain at least 'id' and 'orders' keys."
        )


def test_collection_not_yet_created():
    # The executor is expected to create the 'nested_orders' collection.
    # There must be no leftover typesense data directory with that state present.
    data_dir = os.path.join(PROJECT_DIR, "typesense-data")
    if os.path.isdir(data_dir):
        # If a data dir exists, it must not already contain the target collection state.
        contents = os.listdir(data_dir)
        assert contents == [] or contents == ["."], (
            f"Typesense data directory {data_dir} should be empty before the task begins."
        )
