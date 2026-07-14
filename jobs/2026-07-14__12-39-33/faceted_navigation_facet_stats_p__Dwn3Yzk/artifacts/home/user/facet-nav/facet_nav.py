#!/usr/bin/env python3
"""
facet_nav.py — Faceted navigation CLI backed by Typesense.

Reads a JSON request from stdin, executes the necessary Typesense queries to
implement disjunctive (multi-select) faceting plus numeric price statistics,
and writes a JSON response to stdout.

Disjunctive faceting rule
─────────────────────────
For each categorical facet field F the counts must reflect "what would the
user see if they toggled the selections in F?"  This means the filter on F
itself is EXCLUDED when computing F's counts, while every other active filter
is still applied.

Concretely:
  • brand counts  → filter on category, tags, price   (no brand filter)
  • category counts → filter on brand, tags, price    (no category filter)
  • tags counts   → filter on brand, category, price  (no tags filter)

`found` and `price_stats` are computed with ALL active filters applied.

We achieve this with one "main" Typesense request (all filters, all facets —
used for found + price_stats + any facet whose own filter is inactive) plus up
to three additional "disjunctive" requests, one per categorical facet that has
an active filter.  Typesense's facet_by counts already exclude the filter on
the same field when the filter is built correctly, BUT only if that field's
filter is removed from filter_by for that request.  We therefore build each
request explicitly.
"""

import json
import sys
from typing import Any

import typesense

# ── Connection ───────────────────────────────────────────────────────────────

CLIENT = typesense.Client(
    {
        "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
        "api_key": "xyz",
        "connection_timeout_seconds": 10,
    }
)

COLLECTION = "products"
CATEGORICAL_FACETS = ["brand", "category", "tags"]


# ── Filter building ──────────────────────────────────────────────────────────

def build_filter_by(
    filters: dict[str, Any],
    exclude_field: str | None = None,
) -> str:
    """
    Convert the *filters* dict into a Typesense filter_by string.

    *exclude_field* — when given, the filter for that categorical field is
    omitted (used for disjunctive faceting).
    """
    parts: list[str] = []

    for field in CATEGORICAL_FACETS:
        if field == exclude_field:
            continue
        values: list[str] = filters.get(field) or []
        if values:
            # [v1, v2, ...] means OR within the field (multi-select)
            escaped = [v.replace("`", "\\`") for v in values]
            parts.append(f"{field}:[{','.join(escaped)}]")

    price_filter: dict[str, float] = filters.get("price") or {}
    if price_filter:
        lo = price_filter.get("min")
        hi = price_filter.get("max")
        if lo is not None and hi is not None:
            parts.append(f"price:[{lo}..{hi}]")
        elif lo is not None:
            parts.append(f"price:>={lo}")
        elif hi is not None:
            parts.append(f"price:<={hi}")

    return " && ".join(parts) if parts else ""


# ── Typesense query helpers ──────────────────────────────────────────────────

def _search(params: dict[str, Any]) -> dict[str, Any]:
    return CLIENT.collections[COLLECTION].documents.search(params)


def build_base_params(
    q: str,
    filter_by: str,
    facet_fields: list[str],
    max_facet_values: int,
    facet_query: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "q": q,
        "query_by": "product_name" if q != "*" else "product_name",
        "filter_by": filter_by,
        "facet_by": ",".join(facet_fields),
        "max_facet_values": max_facet_values,
        "per_page": 0,          # we only need aggregates, not hits
        "facet_sample_threshold": 0,   # exact counts (no sampling)
    }
    if q == "*":
        params["q"] = "*"
        # For wildcard queries Typesense needs query_by but it's ignored
    if facet_query:
        params["facet_query"] = facet_query
    return params


# ── Main logic ───────────────────────────────────────────────────────────────

def run(request: dict[str, Any]) -> dict[str, Any]:
    q: str = request.get("q", "*") or "*"
    filters: dict[str, Any] = request.get("filters") or {}
    facet_query_spec: dict[str, str] | None = request.get("facet_query")
    max_facet_values: int = int(request.get("max_facet_values") or 10)

    # Determine which categorical facets have an active filter
    active_cat_filters = {
        f for f in CATEGORICAL_FACETS if filters.get(f)
    }

    # ── 1. Main request (ALL filters) ────────────────────────────────────────
    # Used for: found, price_stats, and counts for any facet with NO active
    # filter of its own (because disjunctive = main result when no own-filter).
    main_filter = build_filter_by(filters)

    # Always facet on price for stats; include all categorical facets
    all_facet_fields = CATEGORICAL_FACETS + ["price"]

    main_params = build_base_params(
        q=q,
        filter_by=main_filter,
        facet_fields=all_facet_fields,
        max_facet_values=max_facet_values,
    )

    main_result = _search(main_params)

    # ── 2. Disjunctive requests (one per active categorical filter) ───────────
    # For each categorical field that has an active filter, we re-run WITHOUT
    # that field's filter so Typesense returns counts across all its values.
    disjunctive_results: dict[str, dict[str, Any]] = {}

    for field in active_cat_filters:
        dis_filter = build_filter_by(filters, exclude_field=field)
        dis_params = build_base_params(
            q=q,
            filter_by=dis_filter,
            facet_fields=[field],
            max_facet_values=max_facet_values,
        )
        disjunctive_results[field] = _search(dis_params)

    # ── 3. facet_query request (optional) ────────────────────────────────────
    fq_result: dict[str, Any] | None = None
    if facet_query_spec:
        fq_field: str = facet_query_spec.get("field", "")
        fq_prefix: str = facet_query_spec.get("prefix", "")

        if fq_field and fq_prefix:
            # Use the disjunctive filter for that field (exclude its own filter)
            fq_filter = build_filter_by(filters, exclude_field=fq_field)
            fq_params = build_base_params(
                q=q,
                filter_by=fq_filter,
                facet_fields=[fq_field],
                max_facet_values=max_facet_values,
                facet_query=f"{fq_field}:{fq_prefix}",
            )
            fq_result = _search(fq_params)

    # ── 4. Assemble the response ──────────────────────────────────────────────

    # found — from the main (all-filter) result
    found: int = main_result.get("found", 0)

    # price_stats — from the main result's facet_counts for "price"
    price_stats = _extract_price_stats(main_result)

    # facets — combine main + disjunctive results
    facets: dict[str, list[dict[str, Any]]] = {}
    for field in CATEGORICAL_FACETS:
        if field in disjunctive_results:
            # Use the disjunctive result (own filter excluded) for this field
            source = disjunctive_results[field]
        else:
            # No active filter on this field → main result is correct
            source = main_result
        facets[field] = _extract_facet_counts(source, field)

    # facet_query_matches
    response: dict[str, Any] = {
        "found": found,
        "facets": facets,
        "price_stats": price_stats,
    }

    if fq_result is not None and facet_query_spec:
        fq_field = facet_query_spec.get("field", "")
        response["facet_query_matches"] = _extract_facet_counts(fq_result, fq_field)

    return response


# ── Extraction helpers ────────────────────────────────────────────────────────

def _find_facet_counts(result: dict[str, Any], field: str) -> dict | None:
    """Return the raw facet_counts entry for *field* from a Typesense result."""
    for fc in result.get("facet_counts", []):
        if fc.get("field_name") == field:
            return fc
    return None


def _extract_facet_counts(
    result: dict[str, Any], field: str
) -> list[dict[str, Any]]:
    """Return [{value, count}, ...] sorted by count desc for *field*."""
    fc = _find_facet_counts(result, field)
    if fc is None:
        return []
    counts = fc.get("counts", [])
    items = [
        {"value": c["value"], "count": c["count"]}
        for c in counts
    ]
    items.sort(key=lambda x: x["count"], reverse=True)
    return items


def _extract_price_stats(result: dict[str, Any]) -> dict[str, float]:
    """Extract min/max/avg/sum from the 'price' facet stats."""
    zero_stats: dict[str, float] = {"min": 0, "max": 0, "avg": 0, "sum": 0}

    fc = _find_facet_counts(result, "price")
    if fc is None:
        return zero_stats

    stats: dict[str, Any] = fc.get("stats", {})
    if not stats or result.get("found", 0) == 0:
        return zero_stats

    return {
        "min": round(float(stats.get("min", 0)), 2),
        "max": round(float(stats.get("max", 0)), 2),
        "avg": round(float(stats.get("avg", 0)), 2),
        "sum": round(float(stats.get("sum", 0)), 2),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit("No input provided on stdin.")
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON input: {exc}")

    response = run(request)
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
