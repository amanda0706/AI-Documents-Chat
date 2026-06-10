# Local PostgreSQL + pgvector runtime

**Status:** the core document lifecycle (create / list / get / delete) is now
implemented in `store_pg.py` behind `STORAGE_BACKEND=postgres`.  JSON persistence
remains the default.  Remaining operations (versioning, comments, shares, status,
metadata) are stubs that raise `NotImplementedError` until wired.

---

## What this adds

`docker-compose.yml` includes a `db` service based on the official
[`pgvector/pgvector:pg16`](https://hub.docker.com/r/pgvector/pgvector) image —
PostgreSQL 16 with the `vector` extension pre-installed.

`db/schema.sql` is mounted read-only and applied automatically the first time the
container starts with an empty data volume.  That gives you 10 fully-indexed
tables (users, documents, fragments, embeddings, shares, comments, activity, chats,
messages) and the IVFFlat cosine-distance index ready for the pgvector migration.

---

## Quick start

### Start the full stack (frontend + backend + database)

```bash
docker compose up --build
```

The `db` service will:

1. Pull `pgvector/pgvector:pg16` on first run.
2. Initialize the `luminaclause` database from `db/schema.sql`.
3. Become healthy (pg_isready) before the stack reports ready.

Open:

- frontend → `http://localhost:3000`
- backend API docs → `http://localhost:8000/docs`

> The backend continues to use JSON persistence even when the database is
> running.  The database is available for inspection and future wiring — no
> product behaviour changes.

### Start in detached mode

```bash
docker compose up -d --build
```

---

## Credentials (local development only)

| Setting | Default |
|---|---|
| Host | `127.0.0.1` (localhost only — never exposed beyond your machine) |
| Port | `5432` |
| Database | `luminaclause` |
| User | `luminaclause` |
| Password | `luminaclause_dev` (**dev default — never use in production**) |

Override the password at runtime (no file changes needed):

```bash
DB_PASSWORD=my-strong-secret docker compose up
```

---

## Check database health

```bash
# Service health status (healthy / starting / unhealthy)
docker compose ps db

# Detailed healthcheck output
docker inspect --format='{{json .State.Health}}' $(docker compose ps -q db)

# Quick pg_isready check
docker compose exec db pg_isready -U luminaclause -d luminaclause
```

Expected output when healthy:

```
/var/run/postgresql:5432 - accepting connections
```

---

## Connect with psql

```bash
# Interactive psql session inside the container
docker compose exec db psql -U luminaclause -d luminaclause

# From the host (requires psql installed locally)
psql postgresql://luminaclause:luminaclause_dev@localhost:5432/luminaclause
```

Useful queries once connected:

```sql
-- Verify pgvector extension is loaded
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- List all tables
\dt

-- Check document_embeddings schema (vector column)
\d document_embeddings

-- Top-k cosine similarity search (replace with a real 128-dim vector)
SELECT fragment_id, text,
       1 - (embedding <=> '[0,0,0,...,0]'::vector) AS score
FROM   document_embeddings
ORDER  BY embedding <=> '[0,0,0,...,0]'::vector
LIMIT  5;
```

---

## Stop and restart

```bash
# Stop containers (data volume is preserved)
docker compose down

# Stop and remove containers + anonymous volumes (named volumes preserved)
docker compose down --remove-orphans

# Stop and destroy ALL data (named volumes deleted — fresh start)
docker compose down -v
```

> `docker compose down` without `-v` keeps `db-data` intact.
> Use `-v` only when you want a clean database (e.g. after schema changes).

---

## Using the PostgreSQL backend

### Activate for the running stack

Add these two lines to `backend/.env` (gitignored), then restart the backend:

```bash
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://luminaclause:luminaclause_dev@localhost:5432/luminaclause
```

For Docker Compose the backend reaches the db via its internal hostname:

```bash
DATABASE_URL=postgresql://luminaclause:luminaclause_dev@db:5432/luminaclause
```

### Implemented operations (first slice)

| Operation | Status |
|---|---|
| `create_document` | ✓ implemented |
| `list_documents` | ✓ implemented |
| `get_document` | ✓ implemented |
| `delete_document` | ✓ CASCADE removes fragments, embeddings, shares, comments, activity |
| `create_document_version` | stub — `NotImplementedError` |
| `list_document_versions` | stub — `NotImplementedError` |
| `add_activity` | stub — `NotImplementedError` |
| `share_document` | stub — `NotImplementedError` |
| `add_comment` | stub — `NotImplementedError` |
| `update_review_status` | stub — `NotImplementedError` |
| `update_metadata` | stub — `NotImplementedError` |

Unimplemented operations fail loudly at call time with a message pointing to
`docs/architecture.md` — they never silently fall back to JSON.

### Run PostgreSQL integration tests

Integration tests require a separate `TEST_DATABASE_URL` (never `DATABASE_URL`)
to prevent accidental production-database usage:

```bash
# Spin up the db service if it isn't already running
docker compose up db -d

# Create a dedicated test database
docker compose exec db psql -U luminaclause -c "CREATE DATABASE luminaclause_test;"

# Run only the integration-marked tests
$env:TEST_DATABASE_URL="postgresql://luminaclause:luminaclause_dev@localhost:5432/luminaclause_test"
python -m pytest backend/tests/test_postgres_repository.py -m integration -v
```

Each test class creates a fresh temporary schema, runs real CRUD operations,
verifies CASCADE deletes, then drops the schema in teardown.  They are skipped
automatically when `TEST_DATABASE_URL` is unset.

### Extending the implementation

To implement an additional operation (e.g. `add_comment`):

1. Write the SQL function in `backend/app/store_pg.py` using `%s` placeholders.
2. Replace `self._not_implemented("add_comment")` in
   `PostgresDocumentRepository.add_comment` (`repository.py`) with
   `return _store_pg.add_comment(...)`.
3. Add unit tests in `test_postgres_repository.py` using the mock-cursor pattern.
4. Run the full test suite — JSON-path tests need no changes.

See [`docs/architecture.md`](architecture.md) for the full migration path,
including pgvector retrieval queries and the `EMBED_DIM` upgrade path.

---

## Security notes

- The database port (`5432`) is bound to `127.0.0.1` only — unreachable from
  the network.
- `DB_PASSWORD` defaults to `luminaclause_dev` for developer convenience.
  **This is not a secret.**  Set a strong password before exposing the stack
  to any network or running with real data.
- `backend/.env` is gitignored.  Set `DATABASE_URL` there for local overrides —
  never commit it.
- Docker named volumes (`db-data`) live inside Docker's storage area, not in
  the repository — no database files are ever committed.
