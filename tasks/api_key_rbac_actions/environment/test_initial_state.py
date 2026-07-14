import os
import shutil


TYPESENSE_BINARY = "/usr/local/bin/typesense-server"


def test_typesense_server_binary_installed():
    assert os.path.isfile(TYPESENSE_BINARY), (
        f"Typesense server binary not found at {TYPESENSE_BINARY}."
    )
    assert os.access(TYPESENSE_BINARY, os.X_OK), (
        f"Typesense server binary at {TYPESENSE_BINARY} is not executable."
    )


def test_curl_available():
    assert shutil.which("curl") is not None, (
        "curl is required to interact with the Typesense HTTP API but was not found in PATH."
    )


def test_home_user_directory_exists():
    assert os.path.isdir("/home/user"), (
        "The base working directory /home/user does not exist."
    )
