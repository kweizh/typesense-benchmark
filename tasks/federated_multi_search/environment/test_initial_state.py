import os
import shutil

import pytest

PROJECT_DIR = "/home/user/federated-search"
DATA_DIR = os.path.join(PROJECT_DIR, "data")
DATA_FILES = ["products.jsonl", "articles.jsonl", "users.jsonl"]


def test_typesense_server_binary_available():
    assert os.path.isfile("/usr/local/bin/typesense-server") and os.access(
        "/usr/local/bin/typesense-server", os.X_OK
    ), "typesense-server binary not found or not executable at /usr/local/bin/typesense-server."


def test_python3_available():
    assert shutil.which("python3") is not None, "python3 was not found in PATH."


def test_typesense_python_sdk_importable():
    try:
        import typesense  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.fail(f"The 'typesense' Python SDK is not importable: {exc}")


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_data_directory_exists():
    assert os.path.isdir(DATA_DIR), f"Sample data directory {DATA_DIR} does not exist."


@pytest.mark.parametrize("filename", DATA_FILES)
def test_sample_data_file_exists_and_non_empty(filename):
    path = os.path.join(DATA_DIR, filename)
    assert os.path.isfile(path), f"Expected sample data file {path} does not exist."
    assert os.path.getsize(path) > 0, f"Sample data file {path} is empty."
