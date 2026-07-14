# Multi-Tenant Search Isolation with Typesense Scoped Search API Keys

## Background
You are building the search backend for a SaaS product where many customers (tenants) share a single Typesense collection. Every document carries a `tenant_id` field. You must guarantee **hard multi-tenant isolation**: when a tenant searches, they may only ever see their own documents, and they must never be able to widen their access — even if they tamper with the search request client-side.

Typesense solves this with **Scoped Search API Keys**: starting from a search-only parent key, you cryptographically embed a `filter_by` (and other search parameters) into a derived key. Typesense automatically enforces the embedded parameters on every search made with that key, and the caller cannot override them.

A standalone Typesense v26.0 server binary is pre-installed at `/usr/local/bin/typesense-server`. A multi-tenant dataset is provided at `/home/user/typesense-task/data/documents.jsonl` (JSONLines, one document per line). Each document has these fields: `id` (string), `tenant_id` (string), `title` (string), `category` (string), and `secret_notes` (string, sensitive internal data that tenants must never receive in search responses).

## Requirements
- Start the Typesense server on port `8108` with the bootstrap API key `xyz`, persisting data under the data directory `/home/user/typesense-task/typesense-data`.
- Create a collection named `records` whose schema makes `tenant_id` filterable/faceted and indexes `title` for full-text search.
- Index every document from the provided dataset into the `records` collection.
- Create a **parent search-only API key** whose `actions` are limited to `documents:search` and whose `collections` scope is limited to the `records` collection.
- For **each distinct tenant** present in the dataset, generate a **Scoped Search API Key** derived from that parent key that:
  - embeds a `filter_by` clause restricting results to that tenant's `tenant_id`, and
  - embeds an `exclude_fields` clause that hides the `secret_notes` field from all search responses.
- Verify (in your own script) that each scoped key can retrieve only its own tenant's documents and cannot be tricked into returning another tenant's data.

## Implementation Hints
- Use any interface you like (the official Python `typesense` SDK and `requests` are available), but the scoped-key derivation must be a correct HMAC-SHA256 signature over the embedded parameters using the parent key — prefer the SDK's built-in scoped-key generation so the signature is correct.
- The parent key used to derive scoped keys must have **no permissions other than** `documents:search`; scoped keys derived from a broader key will be rejected by Typesense at search time.
- Discover the set of tenants from the dataset itself; do not hard-code them.
- Remember that embedded `filter_by` clauses are logically AND-ed with any `filter_by` the caller supplies at search time — this is what makes cross-tenant access impossible.
- Project path: `/home/user/typesense-task`
- Data directory (must persist collection + keys on disk): `/home/user/typesense-task/typesense-data`
- Ensure the server is actually running and the collection, parent key, and scoped keys have really been created (this is a one-off job whose effects are checked afterward).
- Write your results to the artifact file `/home/user/typesense-task/scoped_keys.json` as a single JSON object with exactly these keys:
  - `collection`: the collection name (string).
  - `parent_search_key`: the full value of the parent search-only API key (string).
  - `scoped_keys`: an object mapping each `tenant_id` (string) to its generated scoped search API key value (string).

