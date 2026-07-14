# Typesense Many-to-Many JOINs with Async Reference Resolution

## Overview

This project models a social "likes" graph in [Typesense](https://typesense.org/) using three collections:

| Collection | Key fields |
|---|---|
| `users` | `id`, `username` |
| `products` | `id`, `product_name` |
| `likes` | `id`, `user_id` → `users.id`, `product_id` → `products.id` |

Both reference fields in `likes` use **`async_reference: true`**, which allows a `likes` document to be indexed even when the referenced user or product does not yet exist in the database. Typesense resolves the join automatically once the referenced documents are later indexed.

## Directory structure

```
/home/user/typesense-join/
├── start_server.sh   # Start / restart Typesense
├── setup.py          # Create collections and seed data (out-of-order)
├── query.py          # Rerunnable join-query CLI
├── typesense-data/   # Typesense persistence directory
└── logs/             # Typesense log files
```

## Quick start

```bash
cd /home/user/typesense-join

# 1. Start the server (or restart it)
TYPESENSE_API_KEY=xyz ./start_server.sh

# 2. Create collections and seed data
TYPESENSE_API_KEY=xyz python3 setup.py

# 3. Query
python3 query.py --product p1   # which users liked Widget A?
python3 query.py --user u1      # which products did alice like?
```

## Async reference resolution demo

`setup.py` deliberately indexes the following likes **before** the referenced users and products exist:

| Like ID | user_id | product_id |
|---------|---------|------------|
| l1 | u1 (alice) | p1 (Widget A) |
| l2 | u2 (bob) | p1 (Widget A) |
| l3 | u1 (alice) | p2 (Widget B) |

Users and products are indexed **afterwards**. Because `async_reference: true` is set on both reference fields, Typesense queues the resolution and completes it once the referenced documents arrive — the join queries work correctly without any manual re-indexing.

## Query CLI reference

```
python3 query.py --product <product_id>
```
Prints a JSON array of `username` strings of every user who liked that product, sorted ascending, deduped.

```
python3 query.py --user <user_id>
```
Prints a JSON array of `product_name` strings of every product that user liked, sorted ascending, deduped.

If there are no matches, prints `[]`.

## Collection schemas (key excerpts)

### likes

```json
{
  "name": "likes",
  "fields": [
    { "name": "id",         "type": "string" },
    { "name": "user_id",    "type": "string", "reference": "users.id",    "async_reference": true },
    { "name": "product_id", "type": "string", "reference": "products.id", "async_reference": true }
  ]
}
```

## Join query pattern

```
GET /collections/likes/documents/search
  ?q=*
  &query_by=product_id
  &filter_by=product_id:=p1 && $users(id:*)
  &include_fields=$users(username)
```

The `$CollectionName(...)` syntax inside `filter_by` / `include_fields` triggers Typesense's cross-collection JOIN, merging the matched user document into each likes hit.
