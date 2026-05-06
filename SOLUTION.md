# Stage 4B Solution

## Query Performance

### Bottlenecks found

The list, search, and export routes each built their own SQL queries. That made
it easy for behavior to drift and made future optimization harder because every
change had to be repeated in multiple handlers.

The application also relied mostly on single-column indexes while the common
read paths filter by combinations such as country, gender, age, and age group.
At a million-plus rows on a remote PostgreSQL database, those filters can turn
into slower scans and repeated network round trips.

Pagination was offset-based, which is kept for API compatibility, but unsorted
queries did not have deterministic ordering. Under concurrent inserts, page
boundaries could shift between requests. SQLAlchemy SQL logging was also enabled
with `echo=True`, which adds avoidable overhead and noisy logs under load.

### Changes made

I centralized profile page reads into one query helper. List and search now use
the same count, filter, ordering, pagination, and link-building path. Export uses
the same page query builder, so it benefits from the same filters and ordering
without duplicating the route logic.

Unsorted profile queries now order by `created_at DESC, id DESC`. Explicit sorts
still work, and `id DESC` is added as a deterministic tie-breaker. This keeps the
existing page/limit API unchanged while making page results more stable.

I added composite PostgreSQL indexes for the filters expected to be common at
larger scale:

| Index | Why it exists |
| --- | --- |
| `country_id, gender, age` | Speeds up country + gender + age range filters. |
| `country_id, age_group` | Speeds up common country and bucketed-age queries. |
| `gender, age` | Speeds up gender + age range queries. |
| `created_at, id` | Supports deterministic default ordering and pagination. |

The indexes are declared on the SQLAlchemy model for new databases and also
created at startup with `CREATE INDEX IF NOT EXISTS` so existing remote
databases receive the optimization without introducing a migration framework.

The async database engine now uses explicit pooling:

| Setting | Value | Reason |
| --- | --- | --- |
| `echo` | `False` | Avoids verbose SQL logging overhead in normal operation. |
| `pool_size` | `10` | Keeps warm connections for concurrent API traffic. |
| `max_overflow` | `20` | Allows short bursts without immediately timing out. |
| `pool_timeout` | `30` | Fails predictably if the database is saturated. |
| `pool_pre_ping` | `True` | Avoids handing stale remote connections to requests. |
| `pool_recycle` | `1800` | Refreshes long-lived remote connections. |

### Trade-offs

Composite indexes improve read latency and reduce database work for common
filters, but they use extra storage and make writes slightly more expensive.
That trade-off is acceptable here because read traffic dominates and the indexes
match the actual profile query patterns.

Offset pagination is still not ideal for very deep pages, but the API must
remain unchanged in this slice. The deterministic ordering improves correctness
without requiring clients to adopt cursor pagination yet.

## Query Normalization and Cache

### Why normalization comes first

The search endpoint accepts natural-language phrases, but the database only
needs structured filters. Without a canonical filter representation, equivalent
queries such as `Nigerian females between ages 20 and 45` and
`Women aged 20-45 living in Nigeria` would produce different cache entries even
though they ask for the same data.

The parser remains deterministic and rule-based. It now recognizes conservative
synonyms for gender, explicit age-range phrases, demonyms such as `nigerian`,
and location phrases such as `living in Nigeria`. It does not infer intent
beyond those rules and does not use AI or an LLM.

### Canonical filter shape

Before checking the cache, profile filters are converted into a stable
dictionary:

| Field type | Canonical form |
| --- | --- |
| Enum values | Plain strings such as `female` or `adult`. |
| Country codes | Uppercase two-letter codes such as `NG`. |
| Decimal thresholds | Fixed two-decimal strings such as `0.80`. |
| Missing filters | Explicit `null` values. |
| Pagination and sorting | `page`, `limit`, `sort_by`, and `order` are always included. |

The canonical dictionary is JSON-encoded with sorted keys and hashed with
SHA-256. List and search use the same `profiles:query:<hash>` namespace, so a
structured request and a parsed natural-language request can share cached data
when their filters match.

### Cache behavior

The cache is an in-process bounded TTL cache. It stores only successful
list/search page payloads: `total`, `total_pages`, and serialized profile rows.
Links are rebuilt for every response, which keeps search responses faithful to
the current raw `q` text even when the cached data came from an equivalent query.

| Setting | Value | Reason |
| --- | --- | --- |
| TTL | `60` seconds | Reduces repeated database reads while limiting staleness. |
| Max entries | `512` | Prevents unbounded memory growth on limited compute. |
| Eviction | LRU | Keeps recently used analyst queries hot. |
| Locking | `asyncio.Lock` | Keeps concurrent requests from corrupting cache state. |

The cache is cleared after successful profile creation and deletion. The CSV
ingestion implementation will call the same invalidation hook after each
committed upload chunk.

### Trade-offs

An in-process cache is simple and avoids new infrastructure, which fits the
stage constraint against overengineering. The limitation is that each app process
has its own cache, so this is not a cross-instance cache. Results can also be
briefly stale for up to the TTL, but write paths clear the cache immediately
after successful commits.

CSV export is not cached because it returns a file response and is not the main
interactive repeated-query path.

## CSV Data Ingestion

### Upload design

The API now exposes `POST /api/profiles/upload` for admin CSV uploads. It uses
the same API version, authentication, role, CSRF, and rate-limit protections as
other profile write endpoints.

The ingestion path streams the uploaded file as UTF-8 text and parses it with
Python's CSV reader. It does not load the full file into memory. Valid rows are
accumulated into chunks of `5,000`, then inserted with one bulk PostgreSQL
statement per chunk.

Required CSV columns are:

| Column | Handling |
| --- | --- |
| `name` | Trimmed and lowercased using the same rule as `POST /api/profiles`. |
| `gender` | Must be `male` or `female`. |
| `gender_probability` | Must be a decimal from `0` to `1`. |
| `age` | Must be a non-negative integer. |
| `country_id` | Must be a recognized two-letter country code. |
| `country_probability` | Must be a decimal from `0` to `1`. |

`age_group` is derived from `age`, and `country_name` is derived from
`country_id`. Single-profile creation now also stores `country_name`, keeping
manual writes and CSV writes consistent with the model.

### Failure handling

Each row is validated independently. Bad rows are skipped and counted by reason;
one bad row never fails the whole upload. The response reports total rows,
inserted rows, skipped rows, and non-zero skip reasons.

Rows are skipped for:

| Reason | Example |
| --- | --- |
| `missing_fields` | Required field is blank. |
| `invalid_age` | Age is negative or not an integer. |
| `invalid_gender` | Gender is not recognized. |
| `invalid_probability` | Probability is malformed or outside `0..1`. |
| `invalid_country` | Country code is unknown. |
| `duplicate_name` | Name already exists or repeats in the upload. |
| `malformed_row` | Wrong CSV column count or broken decoded text. |

### Bulk writes and idempotency

The service checks existing names once per chunk and inserts remaining rows with
`INSERT ... ON CONFLICT (name) DO NOTHING`. This avoids row-by-row inserts and
keeps concurrent uploads correct under the existing unique `name` constraint.

Each chunk commits independently. If an upload fails midway, previously
committed chunks remain, which matches the partial-success requirement. After a
chunk inserts rows, the profile query cache is invalidated so future list/search
requests do not serve stale data.

### Trade-offs

The upload runs inside the API request instead of using a background worker.
That keeps the implementation practical for the stage constraints and avoids
new infrastructure. The trade-off is that very large uploads occupy one request
for longer, but chunked validation and bulk inserts keep memory usage bounded
and reduce database round trips.
