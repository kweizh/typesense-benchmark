import json
import os
import shutil

PROJECT_DIR = "/home/user/typo-tuning"
DATASET_PATH = os.path.join(PROJECT_DIR, "products.jsonl")
BINARY_PATH = "/usr/local/bin/typesense-server"

EXPECTED_PRODUCTS = {
    "1": {"name": "Wireless Mouse", "brand": "Logitech"},
    "2": {"name": "Mechanical Keyboard", "brand": "Keychron"},
    "3": {"name": "Camera Bag", "brand": "Nikon"},
    "4": {"name": "Gaming Headset", "brand": "Corsair"},
    "5": {"name": "USB Cable", "brand": "Anker"},
    "6": {"name": "Portable Charger", "brand": "Anker"},
    "7": {"name": "Basketball Shoes", "brand": "Nike"},
    "8": {"name": "Water Bottle", "brand": "Hydro"},
    "9": {"name": "Wifi Router", "brand": "Netgear"},
    "10": {"name": "Beach Bag", "brand": "Coast"},
    "11": {"name": "Charter Bus", "brand": "Metro"},
}


def test_typesense_binary_available():
    found = shutil.which("typesense-server") or (
        BINARY_PATH if os.path.isfile(BINARY_PATH) else None
    )
    assert found is not None, (
        "typesense-server binary not found in PATH or at "
        f"{BINARY_PATH}."
    )


def test_typesense_binary_executable():
    assert os.path.isfile(BINARY_PATH), f"{BINARY_PATH} does not exist."
    assert os.access(BINARY_PATH, os.X_OK), (
        f"{BINARY_PATH} exists but is not executable."
    )


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_dataset_file_exists():
    assert os.path.isfile(DATASET_PATH), (
        f"Dataset file {DATASET_PATH} does not exist."
    )


def test_dataset_contents():
    with open(DATASET_PATH) as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    assert len(lines) == len(EXPECTED_PRODUCTS), (
        f"Expected {len(EXPECTED_PRODUCTS)} products in {DATASET_PATH}, "
        f"found {len(lines)}."
    )
    parsed = {}
    for line in lines:
        doc = json.loads(line)
        assert "id" in doc and "name" in doc and "brand" in doc, (
            "Each product must have 'id', 'name', and 'brand' fields; "
            f"offending line: {line}"
        )
        parsed[str(doc["id"])] = {"name": doc["name"], "brand": doc["brand"]}
    for pid, fields in EXPECTED_PRODUCTS.items():
        assert pid in parsed, f"Product id {pid} missing from dataset."
        assert parsed[pid] == fields, (
            f"Product id {pid} has unexpected content: {parsed[pid]} "
            f"(expected {fields})."
        )


def test_typesense_sdk_importable():
    import typesense  # noqa: F401
