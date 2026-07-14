#!/usr/bin/env python3
"""
Typesense typo-tolerance tuning search tool.

This script queries a local Typesense server with a single fixed typo-tolerance
configuration that implements the rules described in the task:

1. Two typos on product names, exact brands.
2. Short-token guard: length-3 tokens are never typo-corrected;
   length-4 tokens may be corrected with one typo.
3. Precise token dropping: drop tokens only when no document contains
   all query words; never drop when at least one document does.
4. Do not over-search typos: once a token has an exact match, do not
   additionally pull in typo variants of that same token.
5. Space split / join as a fallback.
"""

import argparse
import json
import sys

import typesense


# One fixed typo-tolerance configuration that satisfies all rules at once.
SEARCH_PARAMS = {
    # Search over the two string fields, in the required order.
    "query_by": "name,brand",

    # Disable prefix matching so result behavior reflects typo tolerance only.
    "prefix": False,

    # Rule 1: per-field typos. Two on the product name, zero on the brand.
    "num_typos": "2,0",

    # Rule 2: short-token guard.
    # min_len_1typo=4 means a length-3 token is never typo-corrected, while a
    # length-4 token may be corrected with one typo.
    "min_len_1typo": 4,

    # Allow up to two typos on six-letter names such as "camera".
    "min_len_2typo": 6,

    # Rule 4: do not over-search typos.
    # If a token already has at least one exact match in the index, no typo
    # variants of that token are pulled in.
    "typo_tokens_threshold": 1,

    # Rule 3: precise token dropping.
    # If a document contains all of the query words, the result count is >= 1
    # and no tokens are dropped. If no document contains all of the words,
    # tokens are dropped to surface partial matches.
    "drop_tokens_threshold": 1,

    # Rule 5: space split / join as a fallback (default behavior).
    "split_join_tokens": "fallback",
}


def make_client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
            "api_key": "xyz",
            "connection_timeout_seconds": 10,
        }
    )


def search(client: typesense.Client, query: str) -> list[str]:
    params = dict(SEARCH_PARAMS)
    params["q"] = query
    result = client.collections["catalog"].documents.search(params)
    return [hit["document"]["id"] for hit in result.get("hits", [])]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search the Typesense catalog with the fixed typo-tolerance configuration."
    )
    parser.add_argument("--q", required=True, dest="query", help="Query text")
    args = parser.parse_args()

    client = make_client()
    ids = search(client, args.query)
    sys.stdout.write(json.dumps(ids))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())