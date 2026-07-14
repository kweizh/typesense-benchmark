# Deeply Nested Object Indexing & Querying with Typesense

## Background
You are building the search layer for an e-commerce analytics tool backed by [Typesense](https://typesense.org). Each searchable record is a *customer* document whose data is deeply nested: a customer has an array of `orders`, every order has an array of `line_items`, and every line item carries a nested `attributes` object. This is a three-level nesting shape (`orders` -> `line_items[]` -> `attributes{}`), where the intermediate levels are arrays of objects.

Typesense can index and query nested objects, but only when the collection explicitly enables nested fields and the sub-fields buried inside arrays of objects are typed correctly. Your job is to model this schema, index the provided dataset, and expose a small query tool that searches, filters, and facets on the deep nested paths.

## Requirements
- Run a standalone Typesense server locally and create a collection named `nested_orders` that can index the deeply nested customer documents.
- Index every customer document from the provided dataset into that collection.
- Provide a command-line tool that, given a keyword and a color, searches the deeply nested product names, filters by a deeply nested attribute, and reports faceted category counts.

## Implementation Hints
- Project path: `/home/user/nested-search`
- A dataset of customer documents is provided at `/home/user/nested-search/data/orders.jsonl` (JSONL, one customer document per line). Each line looks structurally like:

  ```json
  {
    "id": "cust_1",
    "customer_name": "Alice",
    "orders": [
      {
        "order_id": "o1",
        "line_items": [
          {"sku": "S1", "name": "Wireless Mouse", "category": "Electronics", "price": 29.99, "attributes": {"color": "black", "material": "plastic"}}
        ]
      }
    ]
  }
  ```

- Run Typesense as the native standalone Linux binary (already installed at `/usr/local/bin/typesense-server`). It MUST listen on `http://localhost:8108`, use the API key `xyz`, and store its data under the directory `/home/user/nested-search/typesense-data` (use this exact data directory so the indexed state persists on disk). Leave the server running after indexing.
- The collection MUST be named `nested_orders` and MUST enable nested fields at the collection level. You must **explicitly** type the nested sub-fields you rely on; remember that any field nested inside an array of objects becomes an array type in Typesense. In particular the deep attribute path `orders.line_items.attributes.color` and the deep path `orders.line_items.category` (which must be facetable) have to be indexed, along with the searchable product name path `orders.line_items.name`.
- After creating the schema, index all documents from the dataset (all documents must be searchable).
- Provide the query tool as `Command: python3 /home/user/nested-search/search.py --keyword <text> --color <color>`.
  - It searches the `nested_orders` collection using the keyword against the nested product-name path, keeps only documents that contain a line item whose nested `attributes.color` exactly equals `<color>`, and computes facet counts over the nested `category` path for the matching documents.
  - It must print exactly one JSON object to stdout (and nothing else) with exactly these two keys:
    - `matched_customer_ids`: the list of matching document `id` values, sorted in ascending lexicographic order.
    - `category_facet_counts`: an object mapping each nested `category` value present among the matched documents to the number of matched documents that contain that category (a document is counted once per distinct category it contains).
  - Example shape (values illustrative only): `{"matched_customer_ids": ["cust_1", "cust_2"], "category_facet_counts": {"Electronics": 2, "Kitchen": 1}}`

