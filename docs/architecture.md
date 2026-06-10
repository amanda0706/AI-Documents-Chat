# LuminaClause architecture

```text
Next.js frontend
      |
      v
FastAPI backend
      |
      +--> DocumentRepository interface   (repository.py)
      |       |
      |       +--> JsonDocumentRepository   (default, STORAGE_BACKEND=json)
      |       +--> PostgresDocumentRepository (planned, STORAGE_BACKEND=postgres)
      |               |
      |               +--> store.py / store_pg.py  (filesystem / PostgreSQL)
      |
      +--> EmbeddingIndex         (data/embeddings.json)
      |       |
      |       +--> local_embed()  (hash-projection, 128 dims, no key)
      |       +--> vector_search() (cosine similarity, top-k)
      |
      +--> AnalysisProvider interface
              |
              +--> LocalProvider       (default, no key required)
              +--> ClaudeProvider      (set ANTHROPIC_API_KEY)
              +--> OpenAIProvider      (adapter seam — set OPENAI_API_KEY)
```

## Auth layer

```text
POST /auth/register   — PBKDF2-SHA256 hash + store user → issue JWT
POST /auth/login      — verify credentials → issue JWT
GET  /auth/me         — validate Bearer token → return user profile
```

**Current implementation:** stdlib-only — no extra pip packages.

| Concern         | Implementation                                              |
|-----------------|-------------------------------------------------------------|
| Password hashing| PBKDF2-SHA256, 100 000 iterations, 32-byte random salt      |
| Token signing   | HMAC-SHA256 (HS256 JWT), RFC 7519-compatible                |
| Secret          | `AUTH_SECRET` env var; dev placeholder when unset           |
| User store      | `data/users.json` — migration target: `users` table in PG  |
| Token expiry    | 24 hours                                                    |
| Timing safety   | `hmac.compare_digest` for password and signature checks     |

**Frontend behaviour:** on submit the login/register form calls the backend.
If the backend returns a valid token it is stored in `localStorage` and
validated on every page load via `GET /auth/me`.  If the backend is
unavailable the form falls back to the existing local email-only session
so the demo always works.

**Migration path to production auth:**

1. Set `AUTH_SECRET` to a 256-bit random string in the deployment env.
2. Swap `auth_store.py` for `auth_store_pg.py` (PostgreSQL `users` table).
3. Add HTTPS — JWTs in `Authorization` headers are plaintext over HTTP.
4. Optionally replace the whole auth layer with Clerk, Supabase Auth, or
   Auth0; the frontend already reads `luminaclause:token` from `localStorage`
   so only the token-issuance side needs to change.

## Current mode

- Documents are stored locally.
- Metadata is stored in JSON.
- Analysis runs through a provider interface (`AnalysisProvider`).
- The active provider is deterministic, local, and explainable.
- Provider selection is configuration-driven through `ANALYSIS_PROVIDER`.
- Core API payloads use validated enums and date-shaped metadata fields.

## Provider configuration

**Local mode is the default.** No API key, no network calls, no document text leaves the machine.

| `ANALYSIS_PROVIDER` | Key required | Status |
|---|---|---|
| `local` (default) | none | active — all analysis runs on-device |
| `claude` | `ANTHROPIC_API_KEY` | implemented — sends fragments to Anthropic API |
| `openai` | `OPENAI_API_KEY` | adapter seam ready — SDK calls not yet wired |

Selecting a cloud provider without the matching key raises a clear `ValueError` at startup — no silent fallback. The optional `AI_MODEL` variable overrides the default model for the selected provider.

### Privacy and consent

When `ANALYSIS_PROVIDER=claude` or `openai` is set, retrieved document fragments are sent to the selected third-party API. **Only enable a cloud provider if you have explicit consent from all relevant parties and have reviewed the provider's data-handling and retention terms.** Do not process real sensitive or confidential contracts through a cloud provider without that consent.

## Vector retrieval layer

``embeddings.py`` implements a RAG-ready retrieval layer that maps every
document fragment to a dense float vector.

### Current local embedding function

``local_embed(text)`` uses the **hashing trick**:

1. Tokenise the text into lowercase alphabetic words (≥ 3 characters).
2. Hash each token with MD5; map to a bucket index (``hash mod 128``) and a
   sign (derived from a higher bit).
3. Accumulate signed counts per bucket.
4. L2-normalise to a unit vector so the dot product equals cosine similarity.

Properties: fully deterministic, zero external dependencies, 128 floats per
fragment.  Not semantically meaningful at this scale — words that collide into
the same bucket appear similar even when unrelated.

### Migration to production embeddings

Replace ``local_embed`` with a single function call:

```python
# OpenAI (1536-dim, paid API)
response = client.embeddings.create(model="text-embedding-3-small", input=text)
return response.data[0].embedding

# sentence-transformers (local, GPU-capable, 384-dim)
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
return model.encode(text).tolist()
```

No endpoint changes are required — only ``EMBED_DIM`` and ``local_embed`` in
``embeddings.py`` need updating.

### Migration to pgvector

```sql
-- Store vectors alongside fragment rows
ALTER TABLE fragments
    ADD COLUMN embedding vector(1536);   -- match your embedding dimension

-- ANN index for fast nearest-neighbour search
CREATE INDEX ON fragments
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Nearest-neighbour retrieval query
SELECT fragment_id, text,
       1 - (embedding <=> $query_vec) AS score
FROM   fragments
WHERE  document_id = $doc_id
ORDER  BY embedding <=> $query_vec
LIMIT  $top_k;
```

The ``EmbeddingRecord`` dataclass fields map 1:1 to this table schema.  Swap
``_save_raw`` / ``_load_raw`` in ``embeddings.py`` for an asyncpg/SQLAlchemy
layer to complete the migration without touching the API endpoints.

## Storage interface

``repository.py`` defines a `DocumentRepository` Protocol (PEP 544, structural
typing) that covers all document persistence operations.  Every API route in
``main.py`` calls ``repo.*`` methods — the active repository is selected once
at startup via ``get_repository()`` and stored as ``main.repo``.

```text
STORAGE_BACKEND=json      → JsonDocumentRepository    (default)
STORAGE_BACKEND=postgres  → PostgresDocumentRepository (psycopg2 + DATABASE_URL)
```

``JsonDocumentRepository`` delegates every method to ``store.py`` at call time,
so existing test monkeypatching of ``store.INDEX_FILE`` / ``store.DATA_DIR``
continues to work without any test changes.

### PostgreSQL implementation — first slice (implemented)

``store_pg.py`` (psycopg2-binary) implements the core document lifecycle:

| Operation | Status |
|---|---|
| ``create_document`` | ✓ implemented |
| ``list_documents`` | ✓ implemented |
| ``get_document`` | ✓ implemented |
| ``delete_document`` | ✓ implemented — CASCADE removes fragments, embeddings, shares, comments, activity |
| ``create_document_version`` | stub — ``NotImplementedError`` |
| ``list_document_versions`` | stub — ``NotImplementedError`` |
| ``add_activity`` | stub — ``NotImplementedError`` |
| ``share_document`` | stub — ``NotImplementedError`` |
| ``add_comment`` | stub — ``NotImplementedError`` |
| ``update_review_status`` | stub — ``NotImplementedError`` |
| ``update_metadata`` | stub — ``NotImplementedError`` |

**SQL injection:** every value passes through a ``%s`` parameterised placeholder.
No string formatting is used in any query body.

**Transaction model:** each public function opens its own connection (from
``DATABASE_URL``), commits on success, rolls back on any exception, and closes
the connection in the ``finally`` block.

**Unit tests** mock ``store_pg._connection`` so CI runs without Docker.
**Integration tests** use ``TEST_DATABASE_URL`` (distinct from ``DATABASE_URL``
to prevent accidental production-database usage) and are skipped unless set.

### Completing the PostgreSQL migration

To add a new operation:

1. Implement the function in ``store_pg.py`` using parameterised SQL.
2. Replace the ``_not_implemented()`` call in the matching stub method in
   ``PostgresDocumentRepository`` (``repository.py``) with a delegation to
   the new ``store_pg.*`` function.
3. Add unit tests in ``test_postgres_repository.py`` (mock cursor pattern).
4. Run the existing test suite — JSON-path tests need no changes.

## Future mode

- PostgreSQL stores users, documents, chats, shares, and clause metadata.
  See the full schema plan in [docs/database-schema.md](database-schema.md)
  and the runnable DDL in [db/schema.sql](../db/schema.sql).
- pgvector stores embeddings (migration path documented above and in the schema).
- Object storage keeps the original files.
- ``OpenAIProvider`` SDK calls wired (mirrors the existing ``ClaudeProvider`` pattern).

## Why this split matters

The frontend already speaks to stable backend endpoints, while the backend now speaks to a provider contract. That means the intelligence layer can improve dramatically later without forcing a product rewrite.

## Current local capabilities

- Landing page with product positioning and GitHub CTA.
- Drag-and-drop PDF/TXT upload with visible progress states.
- Document-grounded Q&A with local conversation history and cited fragments.
- Review workflow: comments, status, metadata, deadlines, and activity timeline.
- Archive workflow through `DELETE /documents/{id}` and the UI danger zone.
- API resilience in the frontend so failed backend calls return controlled empty states instead of a framework overlay.

## Container runtime

Docker Compose runs two services:

- `frontend`: Next.js production server on port `3000`.
- `backend`: FastAPI service on port `8000`, with `/app/data` persisted in the `backend-data` volume.

The frontend uses `NEXT_PUBLIC_API_URL=/api` in the browser and `INTERNAL_API_URL=http://backend:8000` for server-side rewrites inside the Docker network.


## Operational readiness

The backend exposes `/health` for uptime checks and `/metrics` for a compact local observability snapshot. Today the metrics are computed from the local JSON store; after deployment they can feed cloud logs, dashboards, or alerting without changing the product workflow.
