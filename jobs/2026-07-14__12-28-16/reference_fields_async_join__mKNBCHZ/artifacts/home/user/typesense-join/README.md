# Typesense Many-to-Many JOINs with Asynchronous Reference Resolution

This project models a social "likes" graph in [Typesense](https://typesense.org)
30.2: users can like many products and each product can be liked by many users
(a many-to-many relationship). The relationship is modeled with a linking
collection (`likes`) whose fields carry `reference` pointers to the `users` and
`products` collections.

Because the ingestion pipeline receives events out of order, both reference
fields on `likes` use `async_reference: true`. This lets a "like" document be
indexed **before** the user or product it points to exists; the references
resolve automatically once the referenced documents are indexed later.

## Layout

```
/home/user/typesense-join/
├── typesense-data/      # persistent Typesense data directory
├── setup.py             # creates collections + seeds data (idempotent)
├── query.py             # rerunnable join-query CLI
└── README.md
```

## Collections

| Collection | Field(s)                                              |
|------------|-------------------------------------------------------|
| `users`    | `username` (string)                                   |
| `products` | `product_name` (string)                               |
| `likes`    | `user_id`    → reference `users.id`,    `async_reference: true`, `optional: true` |
|            | `product_id` → reference `products.id`, `async_reference: true`, `optional: true` |

## Starting the server

```bash
typesense-server \
  --data-dir=/home/user/typesense-join/typesense-data \
  --api-key="${TYPESENSE_API_KEY}" \
  --api-port=8108
```

Wait until `http://localhost:8108/health` returns `{"ok":true}`.

## Setup (create + seed)

```bash
python3 setup.py
```

This is idempotent: it drops existing collections and recreates them. It seeds
the data so that **`likes/like_late` is indexed before `u_late` and `p_late`
exist**, then indexes those referenced documents afterwards and verifies the
async references resolve (→ `zoe` likes `Thingamajig`).

## Querying

```bash
# Usernames of everyone who liked a product (sorted, deduplicated)
python3 query.py --product <product_id>

# Product names of everything a user liked (sorted, deduplicated)
python3 query.py --user <user_id>
```

Both commands print a JSON array to stdout (e.g. `["alice", "bob"]`), or `[]`
when there are no matches. The CLI queries the **live** Typesense server, so it
reflects any data added after seeding.

### How the join works

The CLI filters through the linking `likes` collection and joins the referenced
collection using Typesense's `$JoinedCollection(field)` syntax:

* `--product p1` → `filter_by: product_id:=p1`, `include_fields: $users(username)`
* `--user u1`    → `filter_by: user_id:=u1`,    `include_fields: $products(product_name)`

Results are de-duplicated and sorted ascending before being printed.

## Example output

```bash
$ python3 query.py --product p1
["alice", "bob"]
$ python3 query.py --product p_late
["zoe"]
$ python3 query.py --user u1
["Gadget", "Widget"]
$ python3 query.py --user u_late
["Thingamajig"]
$ python3 query.py --user nobody
[]
```