# Local PostgreSQL + pgvector runtime

**Status:** the backend still uses JSON persistence (`store.py`).  The database
service is provided so the production schema is always runnable locally and ready
to wire.

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

## Wiring the backend to PostgreSQL

The backend reads `DATABASE_URL` from its environment.  The connection is not
active until `store_pg.py` is implemented and `store.py` is swapped out.

When ready:

1. Uncomment `DATABASE_URL` in `docker-compose.yml` (backend service).
2. Add `db` to the backend `depends_on` block (see comment in the file).
3. Implement `backend/app/store_pg.py` with the same function signatures as
   `store.py` (the contract is documented in `docs/database-schema.md`).
4. Change `main.py` imports from `.store` to `.store_pg`.
5. Run existing tests — they monkeypatch the store, so no test changes are needed.

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
