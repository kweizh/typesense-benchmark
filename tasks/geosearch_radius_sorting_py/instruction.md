# Airport Geosearch: Radius Filtering + Distance Sorting (Typesense, Python)

## Background
You are building the backend for an "airports near me" feature powered by [Typesense](https://typesense.org), a typo-tolerant, in-memory search engine. Typesense supports geo queries on `geopoint` fields, letting you filter documents within a radius of a coordinate and sort them by great-circle distance.

A standalone native Typesense server binary is already installed in the environment at `/usr/local/bin/typesense-server` (Docker-in-Docker is NOT available, so run it as a plain background process, not a container). The official Python SDK (`typesense`) is already installed.

A newline-delimited JSON dataset of airports is provided at `/home/user/project/data/airports.jsonl`. Each line looks like:

```json
{"id": "CDG", "name": "Paris Charles de Gaulle", "iata": "CDG", "city": "Paris", "country": "France", "lat": 49.0097, "lng": 2.5479}
```

## Requirements
- Build an index script that creates a Typesense collection named `airports` containing a `location` field of type `geopoint`, and bulk-imports every record from the provided dataset into it.
- Build a search CLI that, given a reference latitude/longitude and a radius in kilometers, returns only the airports whose location lies within that radius AND returns them sorted by ascending distance from the reference point.
- The distance reported for each hit must be the actual geo distance in meters computed by Typesense (not a value you recompute yourself).
- Both scripts must be rerunnable: re-running the index script must reproduce a clean, deterministic `airports` collection.

## Implementation Hints
- Use the `typesense` Python SDK connecting to the local server at host `localhost`, port `8108`, protocol `http`. The API key is provided via the `TYPESENSE_API_KEY` environment variable (value `xyz`).
- A `geopoint` value is a two-element array in `[latitude, longitude]` order — NOT GeoJSON's `[longitude, latitude]`. Getting this order wrong will silently return wrong results.
- Radius filtering uses the `filter_by` search parameter with the form `location:(lat, lng, <radius> km)`; distance sorting uses `sort_by` with the form `location(lat, lng):asc`. Typesense returns the per-hit distance under `geo_distance_meters`.
- Prefer the bulk `import_` documents endpoint over one-by-one inserts.
- Make the index script idempotent (e.g. drop-and-recreate the collection if it already exists) so the collection always ends up with exactly the dataset's records.

### Hard requirements
- Project path: `/home/user/project`
- The Typesense collection MUST be named `airports` and MUST have a field named `location` of type `geopoint`.
- To (re)build the index, the command `python3 /home/user/project/build_index.py` MUST create the `airports` collection and import all airport records from `/home/user/project/data/airports.jsonl`.
- To search, the command `python3 /home/user/project/search.py --lat <lat> --lng <lng> --radius-km <radius>` MUST print to stdout a single JSON object with exactly these top-level keys:
  - `reference`: an object with keys `lat` (number), `lng` (number), `radius_km` (number) echoing the query.
  - `found`: an integer, the number of airports within the radius.
  - `results`: an array of hit objects ordered by ascending distance, where each hit object has exactly the keys `id` (string), `iata` (string), `name` (string), and `distance_meters` (integer, the value Typesense reports in `geo_distance_meters` for that hit).
- Airports outside the radius MUST NOT appear in `results`, and `found` MUST equal the length of `results`. When no airport is within the radius, print `found` as `0` and `results` as an empty array (do not error).
- The server can be started for local development with: `TYPESENSE_API_KEY=xyz /usr/local/bin/typesense-server --data-dir=/home/user/project/typesense-data --api-key=xyz --port=8108 --enable-cors &` and is healthy once `http://localhost:8108/health` returns `{"ok":true}`.

