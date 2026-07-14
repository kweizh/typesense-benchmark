#!/usr/bin/env python3
import argparse
import sys
import os
import json
import time
import socket
import subprocess
import requests

PORT = 8108
API_KEY = "xyz"
BASE_URL = f"http://localhost:{PORT}"
HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json"
}
DATA_DIR = "/home/user/typesense-app/data"
LOG_FILE = "/home/user/typesense-app/typesense.log"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def is_server_healthy():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        if r.status_code == 200:
            return r.json().get("ok") is True
    except Exception:
        pass
    return False

def ensure_server_running():
    if is_server_healthy():
        print("Typesense server is already running and healthy.", file=sys.stderr)
        return
    
    if is_port_in_use(PORT):
        print("Port 8108 is in use but server is not healthy. Waiting for it to become healthy...", file=sys.stderr)
        for _ in range(5):
            if is_server_healthy():
                return
            time.sleep(1)
        
        # Try to kill whatever is using the port
        print("Port 8108 is still not healthy. Attempting to free port...", file=sys.stderr)
        try:
            subprocess.run(["fuser", "-k", f"{PORT}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
        except Exception:
            pass

    print("Starting Typesense server...", file=sys.stderr)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        subprocess.Popen(
            [
                "/usr/local/bin/typesense-server",
                f"--data-dir={DATA_DIR}",
                f"--api-key={API_KEY}",
                f"--api-port={PORT}"
            ],
            stdout=f,
            stderr=f,
            start_new_session=True
        )
    
    for i in range(30):
        if is_server_healthy():
            print("Typesense server started successfully and is healthy.", file=sys.stderr)
            return
        time.sleep(1)
    
    raise RuntimeError("Typesense server failed to start or become healthy.")

def run_setup():
    ensure_server_running()
    
    # 1. Create/recreate collection
    collection_schema = {
        "name": "library",
        "fields": [
            {"name": "title", "type": "string"},
            {"name": "author", "type": "string"},
            {"name": "points", "type": "int32"}
        ],
        "default_sorting_field": "points"
    }
    
    print("Checking if collection 'library' exists...", file=sys.stderr)
    r = requests.get(f"{BASE_URL}/collections/library", headers=HEADERS)
    if r.status_code == 200:
        print("Collection 'library' already exists. Deleting it for a clean, idempotent setup...", file=sys.stderr)
        requests.delete(f"{BASE_URL}/collections/library", headers=HEADERS)
    
    print("Creating collection 'library'...", file=sys.stderr)
    r = requests.post(f"{BASE_URL}/collections", headers=HEADERS, json=collection_schema)
    r.raise_for_status()
    
    # 2. Index documents
    documents = [
        {"id": "1", "title": "The Great Gatsby", "author": "F Scott Fitzgerald", "points": 90},
        {"id": "2", "title": "The Wizard of Oz", "author": "L Frank Baum", "points": 70},
        {"id": "3", "title": "A Wizard of Earthsea", "author": "Ursula K Le Guin", "points": 85},
        {"id": "4", "title": "Harry Potter and the Sorcerers Stone", "author": "J K Rowling", "points": 95},
        {"id": "5", "title": "The Lord of the Rings", "author": "J R R Tolkien", "points": 99}
    ]
    
    print("Indexing documents...", file=sys.stderr)
    for doc in documents:
        r = requests.post(f"{BASE_URL}/collections/library/documents?action=upsert", headers=HEADERS, json=doc)
        r.raise_for_status()
        
    # 3. Create/update stopwords set
    print("Creating/updating stopwords set 'en_stopwords'...", file=sys.stderr)
    stopwords_data = {
        "stopwords": ["the", "a", "of", "and"],
        "locale": "en"
    }
    r = requests.put(f"{BASE_URL}/stopwords/en_stopwords", headers=HEADERS, json=stopwords_data)
    r.raise_for_status()
    
    # 4. Create/update preset
    print("Creating/updating preset 'library_default'...", file=sys.stderr)
    preset_data = {
        "value": {
            "query_by": "title,author",
            "sort_by": "points:desc",
            "stopwords": "en_stopwords"
        }
    }
    r = requests.put(f"{BASE_URL}/presets/library_default", headers=HEADERS, json=preset_data)
    r.raise_for_status()
    
    print("Setup completed successfully.", file=sys.stderr)

def run_search(query, explicit):
    if not is_server_healthy():
        print("Error: Typesense server is not running or healthy. Please run --setup first.", file=sys.stderr)
        sys.exit(1)
        
    params = {}
    if explicit:
        params = {
            "q": query,
            "query_by": "title,author",
            "sort_by": "points:desc",
            "stopwords": "en_stopwords"
        }
    else:
        params = {
            "q": query,
            "preset": "library_default"
        }
        
    r = requests.get(f"{BASE_URL}/collections/library/documents/search", headers=HEADERS, params=params)
    if r.status_code != 200:
        print(f"Error: Search request failed with status {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
        
    res = r.json()
    found = res.get("found", 0)
    hits = [hit["document"]["id"] for hit in res.get("hits", [])]
    
    output = {
        "found": found,
        "hits": hits
    }
    print(json.dumps(output))

def main():
    parser = argparse.ArgumentParser(description="Typesense Search Presets and Stopwords CLI")
    parser.add_argument("--setup", action="store_true", help="Start server, index docs, register stopwords/preset")
    parser.add_argument("--q", type=str, help="Search query string")
    parser.add_argument("--explicit", action="store_true", help="Run search without preset using explicit parameters")
    
    args = parser.parse_args()
    
    if args.setup:
        run_setup()
    elif args.q is not None:
        run_search(args.q, args.explicit)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
