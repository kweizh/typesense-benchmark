#!/usr/bin/env python3
"""
Query script: run a ranked search against the `catalog` collection.

Usage:
    python3 rank.py --query "<q>"

Output:
    Prints ONLY a JSON array of matching document id strings, in ranked order,
    to stdout.  Example:  ["P2", "P1"]

Ranking policy (encoded in Typesense sort_by):
  1. Promotion tier (dominant):  sponsored > featured > none
     Encoded via _eval() conditional filter scoring.
  2. Text relevance within a tier:  more relevant matches first.
     Uses text_match_type=sum_score so that a document matching the query in
     BOTH title and description scores higher than one matching in a single field.
  3. Popularity tiebreaker:  higher popularity first when text relevance ties.
"""

import argparse
import json

import requests

TYPESENSE_HOST = "http://localhost:8108"
API_KEY = "xyz"
COLLECTION_NAME = "catalog"

HEADERS = {
    "X-TYPESENSE-API-KEY": API_KEY,
    "Content-Type": "application/json",
}


def search(query: str) -> list[str]:
    """
    Execute a Typesense search with the conditional relevance ranking policy.

    sort_by uses exactly 3 fields (the maximum allowed):
      1. _eval([ (badge:=sponsored):100, (badge:=featured):50 ]):desc
         — sponsored documents get score 100, featured get 50, all others get 0.
      2. _text_match:desc
         — text relevance (sum of field-level scores) as secondary signal.
      3. popularity:desc
         — numeric tiebreaker when text relevance is equal.
    """
    params = {
        "q": query,
        "query_by": "title,description",
        "query_by_weights": "1,1",
        # sum_score rewards documents that match across multiple fields
        "text_match_type": "sum_score",
        # Promotion tier → text relevance → popularity tiebreaker (3 fields max)
        "sort_by": "_eval([ (badge:=sponsored):100, (badge:=featured):50 ]):desc,_text_match:desc,popularity:desc",
        # Return all matching documents (we only have 6, but be explicit)
        "per_page": 250,
        # Disable token dropping so we only get true matches
        "drop_tokens_threshold": 0,
    }

    r = requests.get(
        f"{TYPESENSE_HOST}/collections/{COLLECTION_NAME}/documents/search",
        headers=HEADERS,
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    hits = data.get("hits", [])
    return [hit["document"]["id"] for hit in hits]


def main():
    parser = argparse.ArgumentParser(description="Ranked search for the catalog collection")
    parser.add_argument("--query", required=True, help="Search query string")
    args = parser.parse_args()

    ids = search(args.query)
    print(json.dumps(ids))


if __name__ == "__main__":
    main()