# Typesense Action-Based RBAC with Fine-Grained API Keys

## Background
Typesense is an open-source, typo-tolerant search engine. Its Keys API can mint fine-grained API keys that are restricted on a per-action and per-collection basis. In this task you will run a standalone Typesense server, use the bootstrap admin key to provision several role-specific keys, and confirm that each key is limited to exactly the operations it was granted (and rejected for everything else). This is about action-based RBAC across distinct keys, not cryptographically scoped single-tenant search keys.

## Requirements
- Run a standalone Typesense server (native Linux binary) on port 8108 with bootstrap API key `xyz`.
- Create two collections, `products` and `orders`. Each must have a searchable string field named `title`. Index at least one document into each collection.
- Using the Keys API, create the following three fine-grained keys with the narrowest scopes that satisfy each role:
  - A **search-only** key that may search any collection, but cannot write documents or manage collections/keys.
  - A **documents-write** key that may write documents (create, upsert, and import) into ONLY the `products` collection, and cannot search and cannot write to any other collection.
  - An **admin** key that may perform all operations on all collections.
- Persist the full generated key values, because Typesense only returns the full key string once, in the creation response.

## Implementation Hints
- Send the bootstrap key `xyz` via the `X-TYPESENSE-API-KEY` header to create the collections and the role keys.
- The `actions` and `collections` arrays on each key control what it may do; choose scopes appropriately (wildcards are allowed where a role legitimately needs them).
- Project path: /home/user/typesense-rbac
- Run Typesense with data directory `/home/user/typesense-rbac/typesense-data`, api key `xyz`, on port `8108`, and confirm it is healthy (`GET /health` returns `{"ok":true}`) before using it.
- Because only the creation response contains the full key value, write the three key values to `/home/user/typesense-rbac/keys.json` as a single JSON object with exactly the keys `search_only`, `products_writer`, and `admin`, each mapped to its corresponding full API key string (all three values must be distinct).
- Both `products` and `orders` must exist as real collections that each have a string field named `title` and contain at least one indexed document.
- Ensure the actions are actually executed (server running, collections created, keys created) and that the `keys.json` artifact exists when you are done.

## Rejection behavior
- When a key lacks the required action or collection scope, Typesense rejects the request with an HTTP 401 or 403 status; it does not silently succeed.
