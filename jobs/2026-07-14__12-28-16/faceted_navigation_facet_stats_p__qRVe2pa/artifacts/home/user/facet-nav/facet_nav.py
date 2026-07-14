#!/usr/bin/env python3
"""
Faceted-navigation query CLI backed by Typesense.

Reads a single JSON request object from **stdin** and writes a single JSON
response object to **stdout**.

Request shape (stdin):
    {
      "q": "*",                                   # optional, defaults to "*"
      "filters": {                                # optional
        "brand": ["Apple"],
        "category": ["Laptops"],
        "tags": ["premium"],
        "price": { "min": 500, "max": 2000 }
      },
      "facet_query": { "field": "brand", "prefix": "sa" },  # optional
      "max_facet_values": 10                       # optional, defaults to 10
    }

Response shape (stdout):
    {
      "found": 6,
      "facets": {
        "brand":  [ { "value": "Apple", "count": 2 }, ... ],
        "category": [ { "value": "Laptops", "count": 6 }, ... ],
        "tags":    [ { "value": "premium", "count": 4 }, ... ]
      },
      "price_stats": { "min": 599.0, "max": 1999.0, "avg": 1199.0, "sum": 7194.0 },
      "facet_query_matches": [ { "value": "Samsung", "count": 3 } ]   # only if facet_query supplied
    }

Multi-select (disjunctive) semantics
-------------------------------------
The facet counts returned for a given facet field reflect all currently active
filters EXCEPT any filter applied to that same field, so a shopper who has
already selected "Apple" still sees the counts of the other brands they could
switch to.  In contrast, `found` and `price_stats` reflect ALL active filters
combined.

This is implemented by issuing one Typesense search per facet field (via the
multi_search endpoint) where that field's own filter is omitted, plus a single
"main" search carrying every filter (used for `found` and `price_stats`).
"""

import json
import sys

import typesense

TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = 8108
TYPESENSE_PROTOCOL = "http"
TYPESENSE_API_KEY = "xyz"

COLLECTION_NAME = "products"

# The string facet fields we always return counts for, in a stable order.
FACET_FIELDS = ["brand", "category", "tags"]


def get_client() -> typesense.Client:
    return typesense.Client(
        {
            "api_key": TYPESENSE_API_KEY,
            "nodes": [
                {
                    "host": TYPESENSE_HOST,
                    "port": str(TYPESENSE_PORT),
                    "protocol": TYPESENSE_PROTOCOL,
                }
            ],
            "connection_timeout_seconds": 5,
        }
    )


def escape_filter_value(value) -> str:
    """
    Escape a single filter value for use inside a Typesense `filter_by` clause.

    Values containing characters that are meaningful in the filter syntax
    (comma, brackets, backtick, or whitespace) are wrapped in backticks so the
    value is treated as a literal string.
    """
    s = str(value)
    if any(ch in s for ch in (",", "[", "]", "`", " ")):
        # Escape any embedded backticks by backslash-escaping them.
        return "`" + s.replace("`", "\\`") + "`"
    return s


def build_filter_by(filters, exclude_field=None) -> str:
    """
    Build a Typesense `filter_by` string from the active filters.

    ``exclude_field`` omits the filter applied to that field, which is what
    enables the disjunctive (multi-select) facet counts.  The price filter is
    never excluded because it is not one of the selectable facet fields.
    """
    if not filters:
        return ""

    parts = []

    # String / string-array facet filters (OR within a field, AND across fields).
    for field in FACET_FIELDS:
        if field == exclude_field:
            continue
        values = filters.get(field)
        if values:
            escaped = [escape_filter_value(v) for v in values]
            parts.append("{}:[{}]".format(field, ",".join(escaped)))

    # Numeric price range filter (inclusive bounds).
    if exclude_field != "price":
        price = filters.get("price")
        if price:
            mn = price.get("min")
            mx = price.get("max")
            if mn is not None and mx is not None:
                parts.append("price:[{}..{}]".format(mn, mx))
            elif mn is not None:
                parts.append("price:[{}..]".format(mn))
            elif mx is not None:
                parts.append("price:[..{}]".format(mx))

    return " && ".join(parts)


def base_search(q, filter_by, max_facet_values, facet_by=None, facet_query=None):
    """
    Construct a single search parameter dict suitable for the multi_search
    endpoint.  We never need the hits themselves, only facet counts / found,
    so ``per_page`` is set to 0.
    """
    search = {
        "collection": COLLECTION_NAME,
        "q": q,
        "query_by": "product_name",
        "filter_by": filter_by,
        "per_page": 0,
        "max_facet_values": max_facet_values,
    }
    if facet_by:
        search["facet_by"] = facet_by
    if facet_query:
        search["facet_query"] = facet_query
    return search


def extract_facet_values(facet_counts, field_name):
    """
    Pull the {value, count} list for a given field out of a Typesense
    facet_counts response, sorted by count descending (ties broken by value
    ascending for determinism).
    """
    for fc in facet_counts or []:
        if fc.get("field_name") == field_name:
            values = [
                {"value": c["value"], "count": c["count"]}
                for c in fc.get("counts", [])
            ]
            values.sort(key=lambda x: (-x["count"], x["value"]))
            return values
    return []


def extract_price_stats(facet_counts):
    """
    Extract min/max/avg/sum from the price facet stats, rounding to 2 decimals.
    Returns zeros if no stats are present (i.e. no matching products).
    """
    for fc in facet_counts or []:
        if fc.get("field_name") == "price":
            stats = fc.get("stats") or {}
            return {
                "min": round(float(stats.get("min", 0)), 2),
                "max": round(float(stats.get("max", 0)), 2),
                "avg": round(float(stats.get("avg", 0)), 2),
                "sum": round(float(stats.get("sum", 0)), 2),
            }
    return {"min": 0, "max": 0, "avg": 0, "sum": 0}


def run_query(client, request):
    q = request.get("q", "*")
    if q is None:
        q = "*"
    filters = request.get("filters") or {}
    max_facet_values = request.get("max_facet_values", 10)
    if max_facet_values is None:
        max_facet_values = 10
    facet_query = request.get("facet_query")

    # --- Build the batch of searches -------------------------------------
    searches = []

    # 1. Main search: ALL filters applied, facet on `price` for stats.
    searches.append(
        base_search(
            q=q,
            filter_by=build_filter_by(filters, exclude_field=None),
            max_facet_values=max_facet_values,
            facet_by="price",
        )
    )

    # 2..4. One disjunctive search per string facet field (omit that field's
    #       own filter so counts reflect "what else could I switch to").
    for field in FACET_FIELDS:
        searches.append(
            base_search(
                q=q,
                filter_by=build_filter_by(filters, exclude_field=field),
                max_facet_values=max_facet_values,
                facet_by=field,
            )
        )

    # 5. Optional facet-value autocomplete (prefix) match.
    if facet_query:
        fq_field = facet_query.get("field")
        fq_prefix = facet_query.get("prefix", "")
        # Disjunctive here too: exclude the queried field's own filter so the
        # autocomplete surfaces values the shopper could still add.
        searches.append(
            base_search(
                q=q,
                filter_by=build_filter_by(filters, exclude_field=fq_field),
                max_facet_values=max_facet_values,
                facet_by=fq_field,
                facet_query="{}:{}".format(fq_field, fq_prefix),
            )
        )

    # --- Execute as a single multi_search request ------------------------
    multi_response = client.multi_search.perform({"searches": searches})
    results = multi_response["results"]

    # --- Assemble the response -------------------------------------------
    main_result = results[0]
    found = main_result.get("found", 0)
    price_stats = extract_price_stats(main_result.get("facet_counts"))

    facets = {}
    for idx, field in enumerate(FACET_FIELDS, start=1):
        facets[field] = extract_facet_values(
            results[idx].get("facet_counts"), field
        )

    response = {
        "found": found,
        "facets": facets,
        "price_stats": price_stats,
    }

    if facet_query:
        fq_result = results[-1]
        fq_field = facet_query.get("field")
        matches = extract_facet_values(fq_result.get("facet_counts"), fq_field)
        response["facet_query_matches"] = matches

    return response


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"error": "empty request"}))
        sys.exit(1)

    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid JSON: {}".format(exc)}))
        sys.exit(1)

    client = get_client()
    response = run_query(client, request)
    print(json.dumps(response))


if __name__ == "__main__":
    main()