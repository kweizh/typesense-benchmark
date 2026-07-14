# Many-to-Many JOINs with Asynchronous Reference Resolution (Typesense)

## Background
You are modeling a social "likes" graph in Typesense, an open-source, typo-tolerant, in-memory search engine. Users can like many products and each product can be liked by many users. This is a many-to-many relationship, which Typesense models with a linking collection whose fields carry `reference` pointers to the two related collections. Your ingestion pipeline receives events out of order, so a "like" event frequently arrives BEFORE the user or product it points to has been indexed. The reference fields must therefore resolve asynchronously, and the resolution must complete automatically once the referenced documents are indexed later.

## Requirements
- Run a Typesense server locally and model the relationship with three collections: `users`, `products`, and a linking collection `likes`.
- The `users` collection must contain a `username` field, and the `products` collection must contain a `product_name` field.
- The `likes` collection must contain two reference fields: one pointing to the `id` of `users` and one pointing to the `id` of `products`. Both reference fields must resolve asynchronously, so that a like can be indexed even when the referenced user or product does not exist yet.
- Seed the collections such that at least one `likes` document is indexed BEFORE the user and the product it references, then index those users/products afterwards and confirm the references resolve.
- Provide a rerunnable query CLI that answers many-to-many join queries by filtering through the linking collection.

## Implementation Hints
- The Typesense server binary is preinstalled at `/usr/local/bin/typesense-server`. Start it on port 8108, reading the API key from the `TYPESENSE_API_KEY` environment variable, and use `/home/user/typesense-join/typesense-data` as the data directory so the collections persist across restarts. Wait until `http://localhost:8108/health` returns `{"ok":true}` before using it.
- Model the many-to-many relationship with a linking collection and Typesense `reference` fields; enable asynchronous reference resolution on both reference fields of `likes`.
- Cross-collection join queries are expressed with the `$JoinedCollection(...)` syntax inside `filter_by` / `include_fields`.
- Project path: /home/user/typesense-join
- The collections MUST be named exactly `users`, `products`, and `likes`. Inside `likes`, the reference field pointing to `users` MUST be named `user_id` (referencing `users.id`) and the reference field pointing to `products` MUST be named `product_id` (referencing `products.id`).
- Command: `python3 query.py --product <product_id>` — print to stdout a JSON array of the `username` values (strings) of every user who liked that product, sorted in ascending order and with duplicates removed.
- Command: `python3 query.py --user <user_id>` — print to stdout a JSON array of the `product_name` values (strings) of every product that user liked, sorted in ascending order and with duplicates removed.
- If there are no matches, print an empty JSON array `[]`.
- The CLI must query the live Typesense server on port 8108 and reflect any data added to the server after your seeding step (it must not read from a cached local copy).

