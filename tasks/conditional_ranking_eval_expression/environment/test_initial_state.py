import os
import shutil

PROJECT_DIR = "/home/user/typesense-ranking"
TYPESENSE_BINARY = "/usr/local/bin/typesense-server"


def test_typesense_server_binary_available():
    assert os.path.isfile(TYPESENSE_BINARY), (
        f"Typesense server binary not found at {TYPESENSE_BINARY}."
    )
    assert os.access(TYPESENSE_BINARY, os.X_OK), (
        f"Typesense server binary at {TYPESENSE_BINARY} is not executable."
    )


def test_python3_available():
    assert shutil.which("python3") is not None, (
        "python3 was not found in PATH."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )
