import os
import shutil

TYPESENSE_BIN = "/usr/local/bin/typesense-server"
PROJECT_DIR = "/home/user/geo-search"


def test_typesense_server_binary_installed():
    assert os.path.isfile(TYPESENSE_BIN) and os.access(TYPESENSE_BIN, os.X_OK), (
        f"Typesense server binary is not installed or not executable at {TYPESENSE_BIN}."
    )


def test_typesense_server_on_path():
    assert shutil.which("typesense-server") is not None, (
        "typesense-server binary was not found in PATH."
    )


def test_python3_available():
    assert shutil.which("python3") is not None, (
        "python3 interpreter was not found in PATH."
    )


def test_curl_available():
    assert shutil.which("curl") is not None, (
        "curl was not found in PATH; it is needed to talk to the Typesense HTTP API."
    )


def test_typesense_python_sdk_importable():
    import importlib.util

    assert importlib.util.find_spec("typesense") is not None, (
        "The 'typesense' Python SDK is not importable in the environment."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Expected project directory {PROJECT_DIR} to exist before the task starts."
    )
