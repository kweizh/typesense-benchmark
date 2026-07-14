#!/usr/bin/env python3
import sys
import json
import typesense

def get_filter_by(filters, exclude_field=None):
    if not filters:
        return None
    clauses = []
    
    # brand filter
    if 'brand' in filters and filters['brand'] and exclude_field != 'brand':
        vals = ", ".join(f"`{v}`" for v in filters['brand'])
        clauses.append(f"brand:=[{vals}]")
        
    # category filter
    if 'category' in filters and filters['category'] and exclude_field != 'category':
        vals = ", ".join(f"`{v}`" for v in filters['category'])
        clauses.append(f"category:=[{vals}]")
        
    # tags filter
    if 'tags' in filters and filters['tags'] and exclude_field != 'tags':
        vals = ", ".join(f"`{v}`" for v in filters['tags'])
        clauses.append(f"tags:=[{vals}]")
        
    # price filter
    if 'price' in filters and filters['price'] and exclude_field != 'price':
        p = filters['price']
        if 'min' in p and p['min'] is not None:
            clauses.append(f"price:>={p['min']}")
        if 'max' in p and p['max'] is not None:
            clauses.append(f"price:<={p['max']}")
            
    return " && ".join(clauses) if clauses else None

def parse_facet(result_obj, field_name):
    facet_counts = result_obj.get('facet_counts', [])
    field_facet = next((fc for fc in facet_counts if fc['field_name'] == field_name), None)
    if not field_facet:
        return []
    counts = []
    for item in field_facet.get('counts', []):
        counts.append({
            "value": item['value'],
            "count": item['count']
        })
    # Sort by count descending, then alphabetically on value
    counts.sort(key=lambda x: (-x['count'], x['value']))
    return counts

def main():
    # Read from stdin
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            # If empty, exit or return empty JSON
            return
        request_data = json.loads(input_data)
    except Exception as e:
        print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}), file=sys.stderr)
        sys.exit(1)

    # Extract inputs
    user_q = request_data.get('q') or '*'
    filters = request_data.get('filters') or {}
    facet_query = request_data.get('facet_query')
    max_facet_values = request_data.get('max_facet_values')
    if max_facet_values is None:
        max_facet_values = 10

    # Initialize Typesense client
    client = typesense.Client({
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'api_key': 'xyz',
        'connection_timeout_seconds': 5
    })

    # Build the multi_search payload
    searches = []

    # 0: Main query (for found and price_stats)
    main_filter = get_filter_by(filters, exclude_field=None)
    main_q = {
        'collection': 'products',
        'q': user_q,
        'query_by': 'product_name',
        'facet_by': 'price',
        'max_facet_values': 10000, # to ensure exact stats
        'facet_strategy': 'exhaustive',
        'per_page': 0 # we don't need hits
    }
    if main_filter:
        main_q['filter_by'] = main_filter
    searches.append(main_q)

    # 1: Brand query
    brand_filter = get_filter_by(filters, exclude_field='brand')
    brand_q = {
        'collection': 'products',
        'q': user_q,
        'query_by': 'product_name',
        'facet_by': 'brand',
        'max_facet_values': max_facet_values,
        'facet_strategy': 'exhaustive',
        'per_page': 0
    }
    if brand_filter:
        brand_q['filter_by'] = brand_filter
    searches.append(brand_q)

    # 2: Category query
    category_filter = get_filter_by(filters, exclude_field='category')
    category_q = {
        'collection': 'products',
        'q': user_q,
        'query_by': 'product_name',
        'facet_by': 'category',
        'max_facet_values': max_facet_values,
        'facet_strategy': 'exhaustive',
        'per_page': 0
    }
    if category_filter:
        category_q['filter_by'] = category_filter
    searches.append(category_q)

    # 3: Tags query
    tags_filter = get_filter_by(filters, exclude_field='tags')
    tags_q = {
        'collection': 'products',
        'q': user_q,
        'query_by': 'product_name',
        'facet_by': 'tags',
        'max_facet_values': max_facet_values,
        'facet_strategy': 'exhaustive',
        'per_page': 0
    }
    if tags_filter:
        tags_q['filter_by'] = tags_filter
    searches.append(tags_q)

    # 4: Autocomplete query (optional)
    if facet_query:
        fq_field = facet_query.get('field')
        fq_prefix = facet_query.get('prefix', '')
        if fq_field:
            # Under disjunctive active filters for that field
            fq_filter = get_filter_by(filters, exclude_field=fq_field)
            fq_q = {
                'collection': 'products',
                'q': user_q,
                'query_by': 'product_name',
                'facet_by': fq_field,
                'facet_query': f"{fq_field}:{fq_prefix}",
                'max_facet_values': max_facet_values,
                'facet_strategy': 'exhaustive',
                'per_page': 0
            }
            if fq_filter:
                fq_q['filter_by'] = fq_filter
            searches.append(fq_q)

    # Perform multi-search
    try:
        res = client.multi_search.perform({'searches': searches}, {})
    except Exception as e:
        print(json.dumps({"error": f"Typesense search error: {str(e)}"}), file=sys.stderr)
        sys.exit(1)

    results = res.get('results', [])
    if not results:
        print(json.dumps({"error": "No results returned from Typesense"}), file=sys.stderr)
        sys.exit(1)

    # Parse main query results
    main_res = results[0]
    found = main_res.get('found', 0)

    # Parse price stats
    price_stats = { "min": 0.0, "max": 0.0, "avg": 0.0, "sum": 0.0 }
    if found > 0:
        facet_counts = main_res.get('facet_counts', [])
        price_facet = next((fc for fc in facet_counts if fc['field_name'] == 'price'), None)
        if price_facet and 'stats' in price_facet:
            stats = price_facet['stats']
            price_stats['min'] = float(round(stats.get('min') if stats.get('min') is not None else 0.0, 2))
            price_stats['max'] = float(round(stats.get('max') if stats.get('max') is not None else 0.0, 2))
            price_stats['avg'] = float(round(stats.get('avg') if stats.get('avg') is not None else 0.0, 2))
            price_stats['sum'] = float(round(stats.get('sum') if stats.get('sum') is not None else 0.0, 2))

    # Parse facets
    brand_counts = parse_facet(results[1], 'brand')
    category_counts = parse_facet(results[2], 'category')
    tags_counts = parse_facet(results[3], 'tags')

    # Construct response
    response_obj = {
        "found": found,
        "facets": {
            "brand": brand_counts,
            "category": category_counts,
            "tags": tags_counts
        },
        "price_stats": price_stats
    }

    # Parse facet query matches if requested
    if facet_query and facet_query.get('field'):
        # Autocomplete results are at index 4
        fq_field = facet_query.get('field')
        fq_counts = parse_facet(results[4], fq_field)
        response_obj["facet_query_matches"] = fq_counts

    # Write response to stdout
    print(json.dumps(response_obj))

if __name__ == '__main__':
    main()
