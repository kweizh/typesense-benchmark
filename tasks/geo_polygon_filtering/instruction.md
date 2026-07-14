# Typesense Geo-Polygon Fencing for Delivery Hubs

## Background
A logistics company runs a network of delivery hubs, each tagged with a GPS coordinate and an operational status. Operations staff need to select the hubs that fall inside an arbitrary service zone drawn as a polygon on a map, while ignoring hubs that are temporarily out of service. You will build this capability on top of a local Typesense search engine using a `geopoint` field and Typesense's polygon `filter_by` syntax. This is a point-in-polygon containment test against an arbitrary polygon, NOT a radius/circle search.

## Requirements
- Run a local Typesense server (standalone native binary) on `localhost:8108`, secured with the API key from the `TYPESENSE_API_KEY` environment variable.
- Create a collection named `hubs` that stores each hub's `name` (string), `status` (string, facetable), and `location` (`geopoint`).
- Seed the collection with the exact hub dataset listed below.
- Implement a search CLI that returns the ids of hubs contained within a caller-supplied polygon, optionally excluding hubs whose `status` matches a caller-supplied value.

## Hub Dataset (index all of these exactly)
Each `location` is `[latitude, longitude]`.

| id | name | status | latitude | longitude |
| --- | --- | --- | --- | --- |
| h01 | Alpha | active | 37.78 | -122.42 |
| h02 | Bravo | active | 37.79 | -122.42 |
| h03 | Charlie | active | 37.81 | -122.42 |
| h04 | Delta | active | 37.78 | -122.46 |
| h05 | Echo | active | 37.78 | -122.38 |
| h06 | Foxtrot | active | 37.73 | -122.42 |
| h07 | Golf | active | 37.77 | -122.432 |
| h08 | Hotel | active | 37.77 | -122.438 |
| h09 | India | maintenance | 37.775 | -122.42 |
| h10 | Juliet | maintenance | 37.785 | -122.415 |

## Implementation Hints
- Use Typesense's polygon filter form `location:(lat1,lng1, lat2,lng2, ...)` to test point-in-polygon containment; do not approximate it with a radius search. Combine it with a status exclusion using the not-equal operator inside `filter_by`.
- Remember that a `geopoint` value is ordered `[latitude, longitude]`; sending longitude first will silently place points in the wrong location.
- The server data must survive between the seed step and the search step, so keep a single long-running server process.
- Project path: /home/user/geo-search
- Start command (must launch the Typesense server on port 8108, block until `http://localhost:8108/health` reports healthy, then return; it must be safe to call when the server is already running): `bash /home/user/geo-search/start.sh`
- Seed command (idempotent: (re)creates and repopulates the `hubs` collection): `python3 /home/user/geo-search/seed.py`
- Search command: `python3 /home/user/geo-search/search.py --polygon "<lat1,lng1,lat2,lng2,...>" [--exclude-status <status>]`
  - `--polygon` is a single comma-separated string of alternating latitude/longitude values naming the polygon vertices in order.
  - `--exclude-status` is optional; when provided, hubs whose `status` equals that value must be omitted from the results.
  - The command must print to stdout a single JSON object with exactly one key `hub_ids`, whose value is the list of matching hub ids sorted in ascending lexicographic order, e.g. `{"hub_ids": ["h01", "h02"]}`. Print `{"hub_ids": []}` when nothing matches.

