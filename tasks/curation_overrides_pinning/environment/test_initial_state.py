import os
import shutil

PROJECT_DIR = "/home/user/typesense-curation"
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"


def test_typesense_binary_installed():
    assert os.path.isfile(TYPESENSE_BINARY), (
        f"Typesense server binary not found at {TYPESENSE_BINARY}."
    )
    assert os.access(TYPESENSE_BINARY, os.X_OK), (
        f"Typesense server binary at {TYPESENSE_BINARY} is not executable."
    )


def test_typesense_binary_on_path():
    assert shutil.which("typesense-server") is not None, (
        "typesense-server is not available on PATH."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_requests_library_available():
    import importlib.util

    assert importlib.util.find_spec("requests") is not None, (
        "The 'requests' library is required but not importable."
    )
