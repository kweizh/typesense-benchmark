#!/usr/bin/env python3
"""Faceted-navigation query CLI for the Typesense-backed product catalog.

Reads a single JSON request from stdin and writes a single JSON response to
stdout.

Disjunctive (multi-select) faceting is implemented manually: the count of
each facetable string field is computed against every active filter EXCEPT
the filter applied to that same field.  ``found`` and ``price_stats`` are
computed against ALL active filters combined.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import typesense


COLLECTION_NAME = "products"

# String facet fields that get disjunctive treatment in the response.
STRING_FACET_FIELDS = ("brand", "category", "tags")

# Numeric facet field whose stats are reported separately.
NUMERIC_FACET_FIELD = "price"

# Search field when ``q`` is not the wildcard ``*``.
TEXT_FIELD = "product_name"

# Large enough to guarantee exact numeric stats regardless of dataset size.
EXACT_STATS_FACET_VALUES = 10000

CLIENT = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": "xyz",
        "connection_timeout_seconds": 30,
    }
)


def _escape(value: Any) -> str:
    """Quote a string value for inclusion in a Typesense filter expression."""
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _build_price_clause(price: dict[str, Any]) -> str | None:
    """Build the price range filter clause (inclusive bounds)."""
    parts: list[str] = []
    if "min" in price and price["min"] is not None:
        parts.append(f"price:>={price['min']}")
    if "max" in price and price["max"] is not None:
        parts.append(f"price:<={price['max']}")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "(" + " && ".join(parts) + ")"


def build_filter_by(filters: dict[str, Any] | None, exclude_field: str | None = None) -> str | None:
    """Translate the request's ``filters`` object into a Typesense ``filter_by``
    string.  When ``exclude_field`` is provided, the filter on that field is
    omitted (disjunctive faceting).
    """
    if not filters:
        return None

    clauses: list[str] = []

    for field in STRING_FACET_FIELDS:
        if field == exclude_field:
            continue
        values = filters.get(field)
        if not values:
            continue
        parts = [f"{field}:={_escape(v)}" for v in values]
        clauses.append("(" + " || ".join(parts) + ")")

    if NUMERIC_FACET_FIELD != exclude_field and "price" in filters:
        price_clause = _build_price_clause(filters["price"] or {})
        if price_clause:
            clauses.append(price_clause)

    if not clauses:
        return None
    return " && ".join(clauses)


def _do_search(params: dict[str, Any]) -> dict[str, Any]:
    """Execute a search against the products collection."""
    return CLIENT.collections[COLLECTION_NAME].documents.search(params)


def _base_search_params(q: str, filter_by: str | None) -> dict[str, Any]:
    """Build the search parameters common to every query we issue."""
    params: dict[str, Any] = {
        "q": q,
        "per_page": 0,
    }
    if q != "*":
        params["query_by"] = TEXT_FIELD
    if filter_by:
        params["filter_by"] = filter_by
    return params


def _facet_counts(result: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Pull the counts for ``field`` out of a search response."""
    for entry in result.get("facet_counts", []) or []:
        if entry.get("field_name") == field:
            counts = entry.get("counts") or []
            return [
                {"value": c["value"], "count": c["count"]}
                for c in counts
                if c.get("value") is not None
            ]
    return []


def _sorted_by_count(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort facet values by count descending, with value as tiebreaker."""
    return sorted(values, key=lambda v: (-v["count"], v["value"]))


def _empty_price_stats() -> dict[str, float]:
    return {"min": 0, "max": 0, "avg": 0, "sum": 0}


def _price_stats(result: dict[str, Any]) -> dict[str, float]:
    """Extract numeric statistics from the price facet of a search response."""
    for entry in result.get("facet_counts", []) or []:
        if entry.get("field_name") == NUMERIC_FACET_FIELD:
            stats = entry.get("stats") or {}
            try:
                return {
                    "min": round(float(stats.get("min", 0)), 2),
                    "max": round(float(stats.get("max", 0)), 2),
                    "avg": round(float(stats.get("avg", 0)), 2),
                    "sum": round(float(stats.get("sum", 0)), 2),
                }
            except (TypeError, ValueError):
                return _empty_price_stats()
    return _empty_price_stats()


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    q = request.get("q", "*") or "*"
    filters = request.get("filters") or {}
    max_facet_values = int(request.get("max_facet_values", 10) or 10)
    facet_query = request.get("facet_query")

    full_filter = build_filter_by(filters)

    # --- Main search: ``found`` and ``price_stats`` reflect ALL active filters.
    # Use a large ``max_facet_values`` so the numeric stats are exact.
    main_params = _base_search_params(q, full_filter)
    main_params["facet_by"] = NUMERIC_FACET_FIELD
    main_params["max_facet_values"] = EXACT_STATS_FACET_VALUES
    main_result = _do_search(main_params)

    found = int(main_result.get("found", 0))
    price_stats = _price_stats(main_result)
    if found == 0:
        price_stats = _empty_price_stats()

    # --- Disjunctive facet counts: one search per string facet field.
    facets: dict[str, list[dict[str, Any]]] = {}
    for field in STRING_FACET_FIELDS:
        params = _base_search_params(q, build_filter_by(filters, exclude_field=field))
        params["facet_by"] = field
        params["max_facet_values"] = max_facet_values
        result = _do_search(params)
        facets[field] = _sorted_by_count(_facet_counts(result, field))

    response: dict[str, Any] = {
        "found": found,
        "facets": facets,
        "price_stats": price_stats,
    }

    # --- Optional prefix facet search.
    if facet_query:
        fq_field = facet_query.get("field")
        fq_prefix = facet_query.get("prefix", "")
        if fq_field and fq_field in STRING_FACET_FIELDS:
            params = _base_search_params(
                q, build_filter_by(filters, exclude_field=fq_field)
            )
            params["facet_by"] = fq_field
            params["max_facet_values"] = max_facet_values
            params["facet_query"] = f"{fq_field}:{fq_prefix}"
            result = _do_search(params)
            response["facet_query_matches"] = _sorted_by_count(
                _facet_counts(result, fq_field)
            )

    return response


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        response = {"found": 0, "facets": {}, "price_stats": _empty_price_stats()}
        json.dump(response, sys.stdout)
        return

    request = json.loads(raw)
    response = handle_request(request)
    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()