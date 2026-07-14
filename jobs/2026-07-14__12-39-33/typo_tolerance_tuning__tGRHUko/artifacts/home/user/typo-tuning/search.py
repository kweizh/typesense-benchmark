#!/usr/bin/env python3
"""
Search tool for the Typesense 'catalog' collection.

Typo-tolerance configuration rationale
---------------------------------------
query_by          = "name,brand"
    Search name first (higher relevance), then brand.

num_typos         = "2,0"
    name  → up to 2 character errors allowed.
    brand → 0 typos; brand names must be matched exactly.

min_len_1typo     = 4
    Tokens shorter than 4 chars get NO typo correction.
    A 3-char token is therefore never corrected (rule: short-token guard).
    A 4-char token is eligible for 1-typo correction.

min_len_2typo     = 6
    Tokens shorter than 6 chars get at most 1-typo correction.
    6-letter names (e.g. "camera") are eligible for 2-typo correction,
    satisfying the "two typos on product names" rule even for short words.

typo_tokens_threshold = 1
    As soon as ≥1 exact match exists for a token, Typesense stops
    expanding typo variants for that token ("do not over-search typos").

drop_tokens_threshold = 1
    When a multi-word query finds ≥1 document containing ALL words,
    Typesense will NOT drop any word (no unrelated docs pulled in).
    When zero documents contain all words, it drops the least-common
    word(s) progressively until ≥1 result is found ("precise token dropping").

split_join_tokens = "fallback"
    If the query produces no results as-is, Typesense retries by
    splitting run-together words ("waterbottle" → "water bottle") or by
    joining space-separated words ("basket ball" → "basketball").
    Only triggers on zero-result queries, keeping normal results clean.

prefix            = "false"
    Disable prefix matching so results reflect only typo behavior.
"""

import argparse
import json
import sys

import typesense

# ── Typesense client ──────────────────────────────────────────────────────────
client = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": "xyz",
        "connection_timeout_seconds": 5,
    }
)

# ── Fixed search parameters (same for every query) ────────────────────────────
SEARCH_PARAMS = {
    "query_by": "name,brand",
    # Per-field typo limits: 2 for name, 0 for brand
    "num_typos": "2,0",
    # Short-token guard: len < 4 → no correction; len 4-5 → max 1 typo; len ≥ 6 → max 2 typos
    "min_len_1typo": 4,
    "min_len_2typo": 6,
    # Stop expanding typos for a token once it has ≥1 exact match
    "typo_tokens_threshold": 1,
    # Drop words from multi-word queries only when 0 docs match all words
    "drop_tokens_threshold": 1,
    # Split "waterbottle"→"water bottle" / join "basket ball"→"basketball" as fallback
    "split_join_tokens": "fallback",
    # No prefix matching – typo behavior only
    "prefix": "false",
    # Return enough results to cover the whole small catalog
    "per_page": 250,
}


def search(query: str) -> list[str]:
    results = client.collections["catalog"].documents.search(
        {**SEARCH_PARAMS, "q": query}
    )
    return [hit["document"]["id"] for hit in results.get("hits", [])]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", required=True, help="Search query")
    args = parser.parse_args()

    ids = search(args.q)
    print(json.dumps(ids))


if __name__ == "__main__":
    main()
