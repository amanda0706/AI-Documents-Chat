# LuminaClause — PostgreSQL + pgvector schema

**Status:** production migration target — local JSON store is still the default.

The full runnable DDL is in [`db/schema.sql`](../db/schema.sql).

---

## Why this schema exists now

LuminaClause is intentionally local-first.  Every feature works today without
a database server.  This document records the *intended* production schema so
that:

- the migration from `store.py` (JSON) to asyncpg / SQLAlchemy is a
  well-defined engineering task rather than a design problem;
- the API endpoints and Pydantic models are already shaped around this schema,
  meaning no product rewrites are needed when the storage layer is swapped;
- a recruiter or hiring manager can read exactly how the system would scale.

---

## Tables

### `users`

Stores one row per registered user.  Currently mocked in the frontend with a
local email session and `owner` string fields on documents.

| Column     | Type        | Notes                                  |
|------------|-------------|----------------------------------------|
| `id`       | `UUID`      | PK, `gen_random_uuid()`                |
| `email`    | `TEXT`      | UNIQUE — used as the login identifier  |
| `created_at` | `TIMESTAMPTZ` | —                                |

**Auth migration path:** replace the local email mock with Clerk or Supabase
Auth.  Both can issue JWTs that map to `users.id` via the `sub` claim.

---

### `documents`

One row per upload.  Versions of the same contract share a `version_group_id`.

| Column               | Type        | Notes                                                   |
|----------------------|-------------|---------------------------------------------------------|
| `id`                 | `UUID`      | PK — matches current `uuid4()` format                   |
| `filename`           | `TEXT`      | sanitised upload filename                               |
| `version_group_id`   | `UUID`      | groups all versions of the same contract                |
| `version_number`     | `INT`       | 1-based, incremented per group                          |
| `is_latest_version`  | `BOOLEAN`   | unique partial index ensures only one latest per group  |
| `extraction_method`  | `TEXT`      | `text` \| `pdf` \| `ocr`                               |
| `ocr_applied`        | `BOOLEAN`   | —                                                       |
| `page_count`         | `INT`       | —                                                       |
| `owner_id`           | `UUID`      | FK → `users.id`, nullable until auth is wired           |
| `owner_email`        | `TEXT`      | denormalised for display without a JOIN                 |
| `counterparty`       | `TEXT`      | contract metadata                                       |
| `contract_type`      | `TEXT`      | e.g. `MSA`, `NDA`, `Supplier`                           |
| `effective_date`     | `DATE`      | nullable                                                |
| `expiry_date`        | `DATE`      | nullable — used for deadline reminders                  |
| `renewal_date`       | `DATE`      | nullable — used for renewal reminders                   |
| `review_status`      | `TEXT`      | `draft` \| `in_review` \| `approved` (CHECK constraint)|
| `summary_title`      | `TEXT`      | AI-generated                                            |
| `summary_text`       | `TEXT`      | AI-generated prose summary                              |
| `summary_language`   | `TEXT`      | `en` or `pl`                                            |
| `overall_score`      | `INT`       | 0–100 risk score (100 = no risk)                        |
| `summary_highlights` | `JSONB`     | `list[str]` — key points from the AI summary            |
| `summary_risks`      | `JSONB`     | `list[RiskItem]` — matches `models.RiskItem`            |
| `summary_suggestions`| `JSONB`     | `list[SuggestionItem]`                                  |
| `summary_missing`    | `JSONB`     | `list[MissingClauseItem]`                               |
| `created_at`         | `TIMESTAMPTZ` | —                                                     |
| `updated_at`         | `TIMESTAMPTZ` | application-updated on metadata changes               |

**JSONB rationale:** risks, suggestions, and missing clauses are structured but
vary per document and are always read together with the parent row.  JSONB
avoids extra JOINs while keeping the arrays queryable (e.g.
`summary_risks @> '[{"severity":"high"}]'`).

---

### `document_fragments`

One row per page (PDF) or paragraph (TXT).  The `id` column preserves the
current `"{doc_id}-{index}"` string format so existing fragment references in
the API remain valid after migration.

| Column       | Type   | Notes                             |
|--------------|--------|-----------------------------------|
| `id`         | `TEXT` | PK — `"{doc_uuid}-{page_index}"` |
| `document_id`| `UUID` | FK → `documents.id` CASCADE DELETE |
| `page`       | `INT`  | 1-based page/paragraph number     |
| `text`       | `TEXT` | raw extracted text                |
| `created_at` | `TIMESTAMPTZ` | —                          |

---

### `document_embeddings`  ← pgvector

One row per fragment.  Stores the dense float vector for semantic search.

| Column       | Type          | Notes                                              |
|--------------|---------------|----------------------------------------------------|
| `fragment_id`| `TEXT`        | PK + FK → `document_fragments.id` CASCADE DELETE   |
| `document_id`| `UUID`        | FK → `documents.id` CASCADE DELETE (for fast scans)|
| `page`       | `INT`         | denormalised for query convenience                 |
| `text`       | `TEXT`        | denormalised — avoids JOIN in retrieval queries    |
| `embedding`  | `vector(128)` | 128-dim for local demo; see upgrade note below     |
| `provider`   | `TEXT`        | `local` \| `openai` \| `cohere` etc.              |
| `dim`        | `INT`         | must equal the actual vector dimension             |
| `indexed_at` | `TIMESTAMPTZ` | —                                                  |

**Upgrading the dimension:**

```sql
-- 1. Rebuild with OpenAI dimensions
ALTER TABLE document_embeddings
    ALTER COLUMN embedding TYPE vector(1536);

-- 2. Re-run POST /embeddings/reindex after swapping local_embed()
--    for an OpenAI embeddings call — no endpoint changes required.
```

**Index choices:**

```sql
-- IVFFlat: faster build, slightly lower recall; good for > 100k rows
CREATE INDEX ix_embeddings_ivfflat
    ON document_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);          -- tune: lists ≈ sqrt(row count)

-- HNSW: higher recall, slower build; recommended for < 1M rows
CREATE INDEX ix_embeddings_hnsw
    ON document_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Top-k semantic retrieval query:**

```sql
SELECT
    de.fragment_id,
    de.page,
    de.text,
    1 - (de.embedding <=> $1::vector)  AS score
FROM   document_embeddings de
WHERE  de.document_id = $2
ORDER  BY de.embedding <=> $1::vector
LIMIT  $3;
-- $1 = query embedding (same dim)
-- $2 = document UUID
-- $3 = top_k (1–8)
```

This is an exact drop-in for `vector_search()` in `embeddings.py`.

---

### `document_shares`

Normalised from the `shared_with: list[str]` field on `DocumentDetail`.

| Column              | Type        | Notes                     |
|---------------------|-------------|---------------------------|
| `id`                | `UUID`      | PK                        |
| `document_id`       | `UUID`      | FK → `documents.id`       |
| `shared_with_email` | `TEXT`      | UNIQUE per document       |
| `shared_at`         | `TIMESTAMPTZ` | —                       |

---

### `comments`

Normalised from the `comments: list[CommentItem]` field on `DocumentDetail`.

| Column       | Type        | Notes                  |
|--------------|-------------|------------------------|
| `id`         | `UUID`      | PK                     |
| `document_id`| `UUID`      | FK → `documents.id`    |
| `author`     | `TEXT`      | email or display name  |
| `body`       | `TEXT`      | comment text           |
| `created_at` | `TIMESTAMPTZ` | —                    |

---

### `activity_events`

Normalised from the `activity: list[ActivityItem]` field on `DocumentDetail`.

| Column       | Type        | Notes                                                   |
|--------------|-------------|---------------------------------------------------------|
| `id`         | `UUID`      | PK                                                      |
| `document_id`| `UUID`      | FK → `documents.id`                                     |
| `type`       | `TEXT`      | `upload` \| `question` \| `retrieval` \| `compare` \| `share` \| `comment` \| `status` \| `metadata` \| `version` |
| `label`      | `TEXT`      | human-readable label                                    |
| `detail`     | `TEXT`      | e.g. the question text or new status value              |
| `created_at` | `TIMESTAMPTZ` | —                                                     |

---

### `chats` and `messages`

Persistent multi-turn conversation sessions.  The frontend currently stores
chat history in React state only — this pair of tables is the migration target
for durable conversation history across sessions and devices.

**`chats`**

| Column       | Type        | Notes                    |
|--------------|-------------|--------------------------|
| `id`         | `UUID`      | PK                       |
| `document_id`| `UUID`      | FK → `documents.id`      |
| `user_id`    | `UUID`      | FK → `users.id`, nullable |
| `created_at` | `TIMESTAMPTZ` | —                      |

**`messages`**

| Column      | Type        | Notes                                      |
|-------------|-------------|--------------------------------------------|
| `id`        | `UUID`      | PK                                         |
| `chat_id`   | `UUID`      | FK → `chats.id`                            |
| `role`      | `TEXT`      | `user` \| `assistant` (CHECK constraint)   |
| `content`   | `TEXT`      | answer text or user question               |
| `citations` | `JSONB`     | `list[DocumentFragment]` at answer time    |
| `created_at`| `TIMESTAMPTZ` | —                                        |

---

## Storage interface — migration contract

`backend/app/store.py` exposes these public functions.  A Postgres
implementation needs to provide the same signatures; the API routes in
`main.py` call nothing else from the storage layer:

```python
# Read
def list_documents() -> list[DocumentDetail]: ...
def get_document(doc_id: str) -> DocumentDetail | None: ...
def list_document_versions(doc_id: str) -> list[DocumentDetail]: ...

# Write
def create_document(
    filename: str,
    page_texts: list[str],
    summary: DocumentSummary,
    *,
    version_group_id: str | None = None,
    extraction_method: str = "text",
    owner: str = "",
) -> DocumentDetail: ...

def create_document_version(
    source_doc_id: str,
    filename: str,
    page_texts: list[str],
    summary: DocumentSummary,
    extraction_method: str = "text",
) -> DocumentDetail | None: ...

def delete_document(doc_id: str) -> bool: ...

# Mutations
def add_activity(doc_id: str, item: ActivityItem) -> DocumentDetail | None: ...
def add_comment(doc_id: str, comment: CommentItem) -> DocumentDetail | None: ...
def share_document(doc_id: str, email: str) -> DocumentDetail | None: ...
def update_review_status(doc_id: str, status: str) -> DocumentDetail | None: ...
def update_metadata(doc_id: str, *, owner: str, counterparty: str,
                    contract_type: str, effective_date: str,
                    expiry_date: str, renewal_date: str) -> DocumentDetail | None: ...
```

Similarly, `backend/app/embeddings.py` exposes:

```python
def reindex_document(doc: DocumentDetail, *, provider: str = "local") -> list[EmbeddingRecord]: ...
def vector_search(query: str, doc_id: str, *, top_k: int = 3) -> list[tuple[dict, float]]: ...
def get_document_embeddings(doc_id: str, *, include_vectors: bool = False) -> list[dict]: ...
def delete_document_embeddings(doc_id: str) -> int: ...
```

Swapping either module's internals for asyncpg/SQLAlchemy calls changes zero
API routes, zero Pydantic models, and zero frontend code.

---

## Migration steps (when ready)

1. Provision a PostgreSQL 15+ instance (RDS, Supabase, Render Postgres, etc.).
2. Run `db/schema.sql` against the new database.
3. Set `DATABASE_URL` in the environment.
4. Implement `backend/app/store_pg.py` using the function signatures above.
5. Switch `main.py` imports: `from .store_pg import ...` instead of `.store`.
6. Run the existing test suite — all 121 tests should pass unchanged because
   they mock the store via monkeypatch.
7. Backfill existing documents via a one-time migration script.
8. Swap `local_embed()` in `embeddings.py` for an OpenAI call and upgrade the
   `embedding` column to `vector(1536)`.
9. Deploy.

---

## pgvector quick-start (local testing)

```bash
# Docker
docker run -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  ankane/pgvector

# Apply schema
psql postgresql://postgres:postgres@localhost:5432/postgres \
  -f db/schema.sql
```

```bash
# Python client
pip install asyncpg pgvector sqlalchemy[asyncio]
```
