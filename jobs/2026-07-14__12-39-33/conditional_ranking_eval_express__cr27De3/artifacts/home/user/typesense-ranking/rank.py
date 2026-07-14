"""
rank.py — Conditional relevance ranking against the `catalog` collection
=========================================================================
Usage:
    python3 rank.py --query "Alpine Trek"

Prints a JSON array of matching document `id` strings in ranked order to
stdout, and nothing else.

Ranking policy (encoded into a single Typesense `sort_by` chain):
  1. Promotion tier  — _eval([(badge:=sponsored):3,(badge:=featured):2,(badge:=none):1]):desc
  2. Text relevance  — _text_match(buckets:10):desc  [max_score mode across all queried fields]
  3. Popularity      — popularity:desc
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
import urllib.error

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY    = "xyz"
HOST       = "http://localhost:8108"
COLLECTION = "catalog"

HEADERS = {
    "Content-Type": "application/json",
    "X-TYPESENSE-API-KEY": API_KEY,
}

# ── Sort-by expression ────────────────────────────────────────────────────────
# Signal 1 – promotion tier: sponsored=3 > featured=2 > none=1
#   _eval() assigns a conditional integer score per document based on `badge`.
#
# Signal 2 – text-match score bucketed into 10 buckets so fine-grained
#   relevance differences inside a tier still sort correctly.
#   `text_match_type=max_score` (search param) makes Typesense sum/max the
#   match scores from ALL queried fields, rewarding a doc that matches in
#   both `title` and `description` over one that matches only in `title`.
#
# Signal 3 – popularity: numeric descending tiebreaker.
#
# Typesense accepts at most 3 sort fields — these three cover all signals.
SORT_BY = (
    "_eval([(badge:=sponsored):3,(badge:=featured):2,(badge:=none):1]):desc"
    ",_text_match(buckets:10):desc"
    ",popularity:desc"
)


# ── Search ────────────────────────────────────────────────────────────────────

def search(query: str) -> list:
    params = {
        "q":               query,
        # Search across both text fields so multi-field matches are possible
        "query_by":        "title,description",
        # max_score: Typesense picks the *best* per-field score and rewards
        # documents that accumulate matches across multiple queried fields,
        # unlike the default `keyword` mode which only considers the first match.
        "text_match_type": "max_score",
        "sort_by":         SORT_BY,
        # Return up to 250 results (our dataset is tiny; grab everything)
        "per_page":        "250",
    }

    qs  = "&".join(
        f"{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
        for k, v in params.items()
    )
    url = f"{HOST}/collections/{COLLECTION}/documents/search?{qs}"

    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        sys.exit(f"[rank] HTTP {exc.code}: {text}")

    hits = data.get("hits", [])
    return [hit["document"]["id"] for hit in hits]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the catalog collection and print ranked doc IDs as JSON."
    )
    parser.add_argument("--query", required=True, help="Search query string")
    args = parser.parse_args()

    ids = search(args.query)
    # Print ONLY the JSON array — nothing else on stdout
    print(json.dumps(ids))


if __name__ == "__main__":
    main()
