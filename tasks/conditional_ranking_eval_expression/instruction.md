# Conditional Relevance Ranking with Typesense `_eval()` Scoring

## Background
You are building the search backend for an outdoor-gear catalog powered by **Typesense**, a standalone C++ search engine. Product managers want a single search request that blends *business promotion rules* with *text relevance*: promoted items must float to the top, but within each promotion tier the results must still respect how well each product matches the shopper's query, with a popularity tiebreaker for exact ties.

A standalone Typesense server binary is already installed at `/usr/local/bin/typesense-server`. You must run it locally (native binary, no Docker) and implement the ranking logic against it. Encoding this multi-signal ordering into Typesense's `sort_by` grammar (conditional `_eval()` filter scoring, the special `_text_match` field, and a numeric tiebreaker) is the core of the task.

## Requirements
- Run the Typesense server locally on port `8108` with API key `xyz`, using a persistent data directory.
- Create a collection named `catalog` and index the exact 6 documents listed below (searchable text in `title` and `description`; `badge` is a facetable/filterable category; `popularity` is a numeric field).
- Provide a setup entrypoint that (re)creates and populates the `catalog` collection, and a query entrypoint that runs a search and prints the ranked result.
- The search must return **every** document whose `title`/`description` matches the query and order them by this exact policy:
  1. **Promotion tier first (dominant signal):** documents with `badge` = `sponsored` rank above `badge` = `featured`, which rank above every other document (`badge` = `none`). This tier ordering must override text relevance.
  2. **Text relevance within a tier:** among documents in the same tier, more relevant matches come first. Relevance must account for matches across *all* queried fields, so a product that matches the query text in **both** `title` and `description` is more relevant than one that matches only in `title`.
  3. **Popularity tiebreaker:** if two documents in the same tier have equal text relevance, the one with the higher `popularity` comes first.

## Dataset (index these exactly)
| id | title | description | badge | popularity |
|----|-------|-------------|-------|-----------|
| P1 | Alpine Trek Boots | Alpine Trek ready footwear | featured | 10 |
| P2 | Alpine Trek Jacket | Alpine Trek insulated layer | featured | 80 |
| P3 | Alpine Trek Poles | Summit carbon poles | sponsored | 5 |
| P4 | Alpine Trek Tent | Alpine Trek shelter system | none | 99 |
| P5 | Alpine Trek Gloves | Summit winter gloves | sponsored | 40 |
| P6 | Alpine Trek Socks | Merino wool socks | featured | 100 |

## Implementation Hints
- Use the Typesense HTTP API or an official SDK; query both `title` and `description`.
- The promotion tier is a *conditional score*, not a stored field — express it with Typesense's conditional scoring operator inside `sort_by`, then chain the relevance and numeric signals as subsequent tie-breakers (note: `sort_by` accepts at most 3 fields).
- Getting per-tier text relevance to reward matches across multiple fields requires choosing the correct multi-field text-match scoring mode; Typesense's default mode will not reward extra field matches.
- Start the server yourself before indexing; wait until `http://localhost:8108/health` reports `{"ok":true}`.
- Project path: `/home/user/typesense-ranking`
- Setup command: `python3 setup.py` (must be safe to re-run: drop and recreate the collection, then import all 6 documents).
- Query command: `python3 rank.py --query "<q>"`
- Query output: print **only** a JSON array of the matching document `id` strings, in ranked order, to stdout (e.g. `["P2", "P1"]`). Print nothing else on stdout.

