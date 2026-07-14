# Typesense: Migrate a Vector Field to a New Embedding Dimensionality

## Background
A Typesense search engine (v26.0 standalone binary) is already running locally and serving an existing, populated collection named `notes`. Each note has a `title`, `content`, `category`, and a vector field named `content_embedding` that currently stores **4-dimensional** embeddings (these were produced by the team's previous embedding model).

The team has switched to a new embedding model that produces **8-dimensional** embeddings. Your job is to migrate the live `notes` collection in place so that `content_embedding` stores the new 8-dimensional vectors, without recreating the collection and without losing any existing documents.

The newly computed 8-dimensional embeddings for every existing note have been pre-generated for you.

## Requirements
- Migrate the existing `notes` collection **in place** (do NOT drop and recreate the collection, and do NOT rename it). It must still be named `notes` when you are done.
- After migration, the `content_embedding` field must be a vector field of type `float[]` with `num_dim` equal to `8`.
- Every document that existed before the migration must still exist afterwards, with its `id`, `title`, `content`, and `category` values unchanged.
- Each document's `content_embedding` must be replaced with the corresponding 8-dimensional vector provided in the pre-generated data file.
- Nearest-neighbor vector search against the `content_embedding` field must work after the migration.

## Implementation Hints
- Talk to Typesense over its HTTP API (or an official SDK). The server is reachable at `http://localhost:8108`. If it is not responding on `GET /health`, start it with the helper `/usr/local/bin/start-typesense.sh`.
- The server's API key is `xyz` and must be sent in the `X-TYPESENSE-API-KEY` header on every request.
- Typesense validates every stored document against the target schema when you alter a collection, and a vector field's stored data must match the field's declared `num_dim`. Changing the dimensionality of an existing vector field is therefore not as simple as a single schema edit; think carefully about the order of operations so that the on-disk data and the schema are never in an inconsistent state at the moment of validation.
- The pre-generated new embeddings are provided as JSON Lines at `/home/user/migration/new_vectors.jsonl`. Each line is a JSON object with an `id` (matching an existing document id) and a `content_embedding` array of 8 floats. Do not modify this file.
- Project path: /home/user/migration
- This is a one-off migration against the live server. Ensure the migration is actually executed against the running Typesense instance so the collection state reflects the new schema and vectors.

