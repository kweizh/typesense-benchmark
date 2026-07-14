# Federated Search Backend with Typesense `multi_search`

## Background
[Typesense](https://typesense.org) is an open-source, typo-tolerant search engine. Its `multi_search` endpoint lets you send several search queries in a single HTTP request. In **federated** mode, each query in the batch runs against its own collection and returns an *independent* result set, in the same order as the queries you sent.

You are building the search backend for a site that has three heterogeneous collections — `products`, `articles`, and `users`. A user types one query string, and the backend must fan it out across all three collections in a single federated request and return one grouped result set per collection. Because each collection has a different schema, each sub-query must search that collection's own fields. The backend must also stay resilient: if one collection's sub-query fails, the other collections' results must still be returned.

## Requirements
- Provision the search engine: create the three collections with schemas that match the provided data, and import the provided sample data into them.
- Implement a search command that, given one query string, queries `products`, `articles`, and `users` in a **single federated `multi_search` request** (not one HTTP search request per collection) and prints one grouped result set per collection.
- Each collection must be searched using its own relevant text fields (per-query parameters), while shared parameters are passed once as common parameters.
- Handle a partially-failing batch gracefully: if the sub-query for one collection returns an error, the command must still return the successful collections' results and represent the failing collection with an error entry — without crashing.

## Implementation Hints
- Use the standalone native Typesense Linux server binary (already installed at `/usr/local/bin/typesense-server`). It must be reachable at `http://localhost:8108`. Authenticate with the API key from the `TYPESENSE_API_KEY` environment variable (defaults to `xyz`).
- The sample data is provided as JSONL files: `products.jsonl`, `articles.jsonl`, and `users.jsonl` under `/home/user/federated-search/data/`. Each record has a unique `id`.
- Suggested searchable fields per collection: `products` → `product_name`; `articles` → `title,body`; `users` → `username,full_name`. Remember that in a `multi_search` request, per-query parameters live inside each individual search object while common parameters apply to every search.
- Recall that in federated `multi_search`, an individual failing sub-query does not fail the whole HTTP request — that result slot instead carries an error object (e.g. a `code`/`error` pair). Inspect each result slot rather than assuming every slot has hits.
- Project path: `/home/user/federated-search`
- Provisioning command: `python3 setup.py` — idempotently (re)creates the three collections and imports the JSONL data. Running it more than once must succeed and leave the collections fully populated.
- Search command: `python3 search.py --query "<query>"` — prints a single JSON object to stdout and exits with status code 0.
- Output shape of the search command: a JSON object with a top-level `query` string and a `results` object whose keys are exactly `products`, `articles`, and `users`. For a collection whose sub-query succeeded, its value is an object with an integer `found` (total number of matches) and a `hits` array in which each element is the matched document object (including its `id`). For a collection whose sub-query failed, its value is an object containing an `error` string (and no `hits`). All three keys must always be present.

