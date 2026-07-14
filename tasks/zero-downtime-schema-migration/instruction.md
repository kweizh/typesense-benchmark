# Zero-Downtime Schema Migration with Typesense Collection Aliases

## Background
You are operating a product search service backed by a running **Typesense** search engine (v26.0, native Linux binary). The application never talks to a physical collection directly — it always searches through a virtual **Collection Alias** named `products` so that the underlying data can be swapped without touching application code.

Today the alias `products` points to a physical collection `products_v1`. That collection was created with the `rating` field typed as `int32`, but the product team now needs `rating` to hold fractional scores, so it must become a `float`. Typesense does **not** allow changing an existing field's data type in place — a `PATCH` to alter the type of a field that already has stored data is rejected as an incompatible schema change. The correct approach is a zero-downtime migration using a second collection plus an alias swap.

The Typesense server persists its data (collections, documents, and aliases) to the on-disk data directory at `/home/user/project/typesense-data`. That directory already contains the seeded `products_v1` collection and the `products` alias.

## Requirements
- Start the Typesense server against the existing data directory (do not create a new empty data directory, or you will lose the seeded collection).
- Create a brand-new physical collection whose schema is identical to `products_v1` **except** that the `rating` field is typed as `float` instead of `int32`. Keep every other field, its index/facet options, and the `default_sorting_field` unchanged.
- Reindex **every** document currently in `products_v1` into the new collection with zero data loss. Integer `rating` values must be carried over and coerced to `float`.
- Atomically switch the `products` alias so it points to the new collection instead of `products_v1`, so that searches through the alias never break.
- After the alias points to the new collection, drop the old `products_v1` collection.
- Write a short migration report to a log file.

## Implementation Hints
- Use the real Typesense HTTP API (or an official SDK); do not mock the server. The server listens on `http://localhost:8108` with API key `xyz`.
- The in-place field type change is intentionally impossible — you must migrate to a new collection and swap the alias rather than `PATCH`-ing the type of `rating` on `products_v1`.
- The document export endpoint returns JSONL that can be fed directly into the import endpoint of the new collection; use bulk import and remember that dirty/mismatched primitive types can be coerced during import.
- Resolve the current physical collection behind the alias by reading the alias, and re-point the alias by upserting it to the new collection name.
- Project path: /home/user/project
- Server: start Typesense with `--data-dir=/home/user/project/typesense-data --api-key=xyz --port=8108` (a helper script `/home/user/project/start-typesense.sh` is provided). Ensure `http://localhost:8108/health` reports `{"ok":true}` before migrating.
- The new collection's physical name MUST be different from `products_v1`, and after migration the alias `products` MUST resolve to that new collection while `products_v1` no longer exists.
- Preserve document `id`s and all field values exactly (only the `rating` type changes from `int32` to `float`); the migrated collection must contain the same number of documents as `products_v1` had (no documents lost or added).
- Log file: /home/user/project/migration.log — write a line in the exact format `Migrated <N> documents to <new_collection_name>` (where `<N>` is the number of documents reindexed) and a line `Alias products -> <new_collection_name>`.
- This is a one-off migration: ensure it actually runs and that the resulting Typesense state (new float-typed collection, swapped alias, dropped old collection) is persisted on the server.

