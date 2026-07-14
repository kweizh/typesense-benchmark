# Typesense Search Presets and Stopwords

## Background
You are building a small search backend on top of [Typesense](https://typesense.org), a fast, typo-tolerant in-memory search engine. The Typesense server binary is already installed in the environment at `/usr/local/bin/typesense-server`, but it is **not running**. Two of Typesense's operational features are central to this task:

- **Presets**: a named, server-side bundle of search parameters that a client can reference by name at query time (via the `preset` parameter) instead of resending every parameter on each request.
- **Stopwords sets**: a named list of keywords that Typesense removes from the *search query* (not from indexed documents) before matching.

Your job is to stand up a Typesense instance, index a fixed catalogue of books, register a reusable preset and a stopwords set, and expose a small command-line tool that runs searches. The tool must be able to run the exact same logical search in two ways — driven purely by the stored preset, or by passing the equivalent parameters explicitly — and both must return identical results.

## Requirements
- Start a Typesense server locally on port `8108`, using the API key `xyz` (the standard local key, matching the research setup), with a persistent data directory.
- Create a collection named `library` with these fields: `title` (`string`), `author` (`string`), `points` (`int32`), and set `points` as the `default_sorting_field`.
- Index exactly the following 5 documents (use these `id` values verbatim):

  ```json
  [
    {"id": "1", "title": "The Great Gatsby", "author": "F Scott Fitzgerald", "points": 90},
    {"id": "2", "title": "The Wizard of Oz", "author": "L Frank Baum", "points": 70},
    {"id": "3", "title": "A Wizard of Earthsea", "author": "Ursula K Le Guin", "points": 85},
    {"id": "4", "title": "Harry Potter and the Sorcerers Stone", "author": "J K Rowling", "points": 95},
    {"id": "5", "title": "The Lord of the Rings", "author": "J R R Tolkien", "points": 99}
  ]
  ```

- Create a stopwords set named `en_stopwords` (locale `en`) containing the keywords `the`, `a`, `of`, and `and`.
- Create a preset named `library_default` whose stored parameters query the `title` and `author` fields, sort by `points` in descending order, and apply the `en_stopwords` stopwords set.
- Provide a rerunnable CLI that searches the `library` collection and can either drive the search entirely from the `library_default` preset or from the equivalent parameters passed explicitly.

## Implementation Hints
- Any language/SDK or plain HTTP calls to the Typesense REST API are acceptable; interact with the *real* running server (do not mock it).
- Stopwords are removed from the query at *search* time only — they are not stripped from indexed documents — and Typesense tokenizes and lowercases stopword entries when it stores the set.
- Remember that a preset referenced by the single-collection document-search endpoint must store its `value` as a flat object of search parameters (not a multi-search `searches` array); the `stopwords` set name can be one of those stored parameters.
- Explicit search parameters and the preset must produce identical result sets, so keep the explicit path and the preset content in agreement.
- Setup must be idempotent (safe to run more than once even if the collection, preset, or stopwords set already exists).
- Project path: /home/user/typesense-app
- Setup command: `python3 run.py --setup` — starts/ensures the server, creates the collection, indexes the documents, and registers the `en_stopwords` set and `library_default` preset. It must be safe to re-run.
- Search command: `python3 run.py --q "<query text>"` — runs a search on the `library` collection using **only** the `library_default` preset (send just the preset reference plus the query text `q`; do not resend query_by/sort_by/stopwords).
- Explicit variant: `python3 run.py --q "<query text>" --explicit` — runs the logically equivalent search **without** referencing the preset, passing `query_by`, `sort_by`, and the `stopwords` set explicitly instead.
- Both search commands must print to stdout a single JSON object with exactly the keys `found` (integer total number of matches) and `hits` (an array of the matching document `id` strings, in the order Typesense returns them). Example shape: `{"found": 2, "hits": ["3", "2"]}`.

