# Typesense Search Curation: Pinning, Hiding & Dynamic Filtering

## Background
You are tuning the search experience for an electronics store powered by [Typesense](https://typesense.org). Merchandisers want editorial control over search results: promoting hand-picked products to fixed positions, hiding certain products, and automatically narrowing results by brand for brand-oriented queries. Typesense implements this through **Curation / Overrides**, which take precedence over the relevance ranking.

A Typesense v26.0 standalone server binary is already installed at `/usr/local/bin/typesense-server`. There is no Docker daemon available, so you must run Typesense as a native background process.

## Requirements
- Start a Typesense server as a background process and populate it with a product catalog.
- Create a `catalog` collection and index the products listed below.
- Create **three** override (curation) rules on the `catalog` collection:
  1. An **exact-match** rule that pins and hides products for the query `phone`.
  2. A **contains-match** rule that pins a product for queries containing `deal`.
  3. A **dynamic filtering** rule that turns a `{brand} phone` query pattern into a brand filter.
- The curated documents must appear (or disappear) exactly as specified, regardless of their natural relevance ranking.

## Data

### Collection `catalog`
- `name`: string (the primary searchable field)
- `brand`: string, facetable
- `category`: string, facetable
- `popularity`: int32 (use this as the default sorting field)

### Documents to index
| id | name | brand | category | popularity |
| --- | --- | --- | --- | --- |
| p1 | Apple iPhone 15 | Apple | phone | 50 |
| p2 | Samsung Galaxy phone | Samsung | phone | 95 |
| p3 | Google Pixel phone | Google | phone | 70 |
| p4 | OnePlus 12 phone | OnePlus | phone | 30 |
| p5 | Nokia Classic phone | Nokia | phone | 10 |
| p6 | Refurbished phone deal | Refurb | phone | 5 |
| p7 | Motorola Edge phone | Motorola | phone | 40 |

## Override rules to create
1. **Exact match on `phone`** — when a user searches exactly for `phone`:
   - Pin product `p1` to position 1.
   - Pin product `p7` to position 2.
   - Exclude (hide) product `p2` from the results.
2. **Contains match on `deal`** — when a user's query contains the word `deal`:
   - Pin product `p3` to position 1.
3. **Dynamic brand filter** — for the query pattern `{brand} phone` (a contains-style rule using the `{brand}` placeholder):
   - Dynamically apply a `brand:={brand}` filter derived from the matched brand token.
   - The matched brand token must be removed from the query before searching.

## Implementation Hints
- Project path: `/home/user/typesense-curation`
- Start the server with: `typesense-server --data-dir=/home/user/typesense-curation/typesense-data --api-key=xyz --port=8108 --enable-cors`
- Typesense must be reachable at `http://localhost:8108` with API key `xyz`, and it MUST remain running after your setup completes.
- You may use any interface (the REST API via curl, or a Typesense SDK). Override rules live under `/collections/catalog/overrides/:id`.
- Pinned documents are placed with 1-based positions; excluded documents are removed regardless of relevance. Curation is applied on top of, and overrides, the normal ranking.
- For the dynamic filter rule, remember that a field can only be used in a dynamic `{field}` filter if it is facetable in the schema.
- After configuring everything, write a log file `Log file: /home/user/typesense-curation/setup.log` containing the id of each override rule you created, one id per line.

