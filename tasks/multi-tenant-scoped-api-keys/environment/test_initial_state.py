import json
import os

import pytest

PROJECT_DIR = "/home/user/typesense-task"
DATA_FILE = os.path.join(PROJECT_DIR, "data", "documents.jsonl")
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"


def test_typesense_binary_installed():
    assert os.path.isfile(TYPESENSE_BINARY), (
        f"Typesense server binary not found at {TYPESENSE_BINARY}."
    )
    assert os.access(TYPESENSE_BINARY, os.X_OK), (
        f"Typesense server binary at {TYPESENSE_BINARY} is not executable."
    )


def test_requests_library_available():
    import requests  # noqa: F401


def test_typesense_sdk_available():
    import typesense  # noqa: F401


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_dataset_file_exists():
    assert os.path.isfile(DATA_FILE), (
        f"Multi-tenant dataset file {DATA_FILE} does not exist."
    )


def test_dataset_is_valid_jsonl_with_expected_fields():
    with open(DATA_FILE, encoding="utf-8") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    assert len(lines) > 0, f"Dataset file {DATA_FILE} is empty."
    required_fields = {"id", "tenant_id", "title", "category", "secret_notes"}
    for idx, line in enumerate(lines):
        doc = json.loads(line)
        missing = required_fields - set(doc.keys())
        assert not missing, (
            f"Document on line {idx + 1} is missing fields: {sorted(missing)}."
        )


def test_scoped_keys_artifact_not_yet_created():
    artifact = os.path.join(PROJECT_DIR, "scoped_keys.json")
    assert not os.path.exists(artifact), (
        f"Artifact {artifact} should not exist before the task begins."
    )
