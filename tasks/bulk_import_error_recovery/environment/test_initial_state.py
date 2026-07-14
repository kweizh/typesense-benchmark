import json
import os
import shutil

PROJECT_DIR = "/home/user/import-pipeline"
DATA_FILE = os.path.join(PROJECT_DIR, "data", "raw_products.jsonl")
TYPESENSE_BIN = "/usr/local/bin/typesense-server"

EXPECTED_LINE_COUNT = 209


def test_typesense_server_binary_installed():
    assert os.path.isfile(TYPESENSE_BIN), (
        f"Typesense server binary not found at {TYPESENSE_BIN}."
    )
    assert os.access(TYPESENSE_BIN, os.X_OK), (
        f"Typesense server binary at {TYPESENSE_BIN} is not executable."
    )


def test_python3_available():
    assert shutil.which("python3") is not None, (
        "python3 was not found in PATH; it is required to run the pipeline."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_dataset_file_exists():
    assert os.path.isfile(DATA_FILE), (
        f"Input dataset {DATA_FILE} does not exist."
    )


def test_dataset_line_count():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    assert len(lines) == EXPECTED_LINE_COUNT, (
        f"Expected {EXPECTED_LINE_COUNT} documents in {DATA_FILE}, "
        f"found {len(lines)}."
    )


def test_dataset_lines_are_valid_json():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"Line {i} of {DATA_FILE} is not valid JSON: {exc}"
                )


def test_dataset_contains_expected_edge_case_ids():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        ids = set()
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            if "id" in doc:
                ids.add(doc["id"])
    for expected_id in ["c001", "c002", "f001", "f004", "u001", "u003"]:
        assert expected_id in ids, (
            f"Expected document id '{expected_id}' to be present in the "
            f"initial dataset {DATA_FILE}."
        )
