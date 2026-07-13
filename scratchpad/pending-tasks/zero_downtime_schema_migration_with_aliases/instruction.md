In-place field type alterations (e.g., changing an `int32` to a `float`) fail if existing stored documents cannot be coerced into the new type.

You need to implement a zero-downtime migration script that takes an existing collection `products_v1`, creates a new `products_v2` collection with a modified schema (changing the `rating` field to `float`), reindexes the documents, and swaps a virtual collection alias to point to the new collection in a backend environment.

**Constraints:**
- Must use the Collection Alias API to perform the zero-downtime swap.
- Do NOT attempt to modify the field type of `products_v1` in-place.
- The alias `products` must remain resolvable for search queries at all times during the script execution.