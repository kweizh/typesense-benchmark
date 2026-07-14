import json
import requests

TYPESENSE_URL = "http://localhost:8108"
API_KEY = "xyz"
HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

def migrate():
    # 1. Read new vectors from the jsonl file
    vectors = []
    with open("/home/user/migration/new_vectors.jsonl", "r") as f:
        for line in f:
            if line.strip():
                vectors.append(json.loads(line))
    
    print(f"Loaded {len(vectors)} new vectors from file.")

    # 2. Update each document in place with the new vector
    for vec_data in vectors:
        doc_id = vec_data["id"]
        embedding = vec_data["content_embedding"]
        
        # Patch the document
        url = f"{TYPESENSE_URL}/collections/notes/documents/{doc_id}"
        payload = {
            "content_embedding": embedding
        }
        response = requests.patch(url, json=payload, headers=HEADERS)
        if response.status_code == 200:
            print(f"Successfully updated document {doc_id}")
        else:
            print(f"Failed to update document {doc_id}: {response.status_code} - {response.text}")
            raise Exception("Migration failed during document update.")

    # 3. Add the field back to the schema with num_dim = 8
    print("Adding content_embedding field back to schema with num_dim=8...")
    schema_patch = {
        "fields": [
            {
                "name": "content_embedding",
                "type": "float[]",
                "num_dim": 8,
                "vec_dist": "cosine",
                "hnsw_params": {
                    "M": 16,
                    "ef_construction": 200
                }
            }
        ]
    }
    
    url = f"{TYPESENSE_URL}/collections/notes"
    response = requests.patch(url, json=schema_patch, headers=HEADERS)
    if response.status_code == 200:
        print("Successfully updated schema with 8-dimensional content_embedding!")
        print(response.json())
    else:
        print(f"Failed to update schema: {response.status_code} - {response.text}")
        raise Exception("Migration failed during schema update.")

if __name__ == "__main__":
    migrate()
