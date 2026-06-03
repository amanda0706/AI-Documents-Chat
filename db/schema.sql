-- =============================================================================
-- LuminaClause — PostgreSQL + pgvector schema
-- =============================================================================
-- Target: PostgreSQL 15+ with pgvector 0.7+
-- Local default: JSON filesystem store (backend/app/store.py)
-- This file is the migration target, not an active migration runner.
--
-- Apply order:
--   1. Enable extension
--   2. Core tables (users, documents)
--   3. Child tables (fragments, embeddings, shares, comments, activity, chat)
--   4. Indexes
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector — run after: pip install pgvector


-- ---------------------------------------------------------------------------
-- 1. Users
--    Currently mocked in the frontend with a local email session.
--    This table is the migration target for Clerk, Supabase Auth, or JWT.
-- ---------------------------------------------------------------------------

CREATE TABLE users (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email      TEXT        NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 2. Documents
--    One row per upload / version.  Versions are grouped by version_group_id.
--    Matches backend/app/models.py :: DocumentDetail.
-- ---------------------------------------------------------------------------

CREATE TABLE documents (
    -- identity
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filename            TEXT        NOT NULL,

    -- versioning
    version_group_id    UUID        NOT NULL,   -- all versions of the same contract share this
    version_number      INT         NOT NULL DEFAULT 1,
    is_latest_version   BOOLEAN     NOT NULL DEFAULT TRUE,

    -- extraction
    extraction_method   TEXT        NOT NULL DEFAULT 'text',   -- 'text' | 'pdf' | 'ocr'
    ocr_applied         BOOLEAN     NOT NULL DEFAULT FALSE,
    page_count          INT         NOT NULL DEFAULT 0,

    -- ownership (denormalised email for display; FK added when auth is real)
    owner_id            UUID        REFERENCES users(id) ON DELETE SET NULL,
    owner_email         TEXT        NOT NULL DEFAULT '',

    -- contract metadata
    counterparty        TEXT        NOT NULL DEFAULT '',
    contract_type       TEXT        NOT NULL DEFAULT '',
    effective_date      DATE,
    expiry_date         DATE,
    renewal_date        DATE,

    -- review workflow
    review_status       TEXT        NOT NULL DEFAULT 'draft'
                            CHECK (review_status IN ('draft', 'in_review', 'approved')),

    -- AI-generated summary (structured scalars)
    summary_title       TEXT        NOT NULL DEFAULT '',
    summary_text        TEXT        NOT NULL DEFAULT '',
    summary_language    TEXT        NOT NULL DEFAULT 'en',
    overall_score       INT         NOT NULL DEFAULT 100
                            CHECK (overall_score BETWEEN 0 AND 100),

    -- AI-generated summary (structured arrays stored as JSONB)
    -- Each array element matches the corresponding Pydantic model in models.py
    summary_highlights  JSONB       NOT NULL DEFAULT '[]',   -- list[str]
    summary_risks       JSONB       NOT NULL DEFAULT '[]',   -- list[RiskItem]
    summary_suggestions JSONB       NOT NULL DEFAULT '[]',   -- list[SuggestionItem]
    summary_missing     JSONB       NOT NULL DEFAULT '[]',   -- list[MissingClauseItem]

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enforce a single latest version per version group
CREATE UNIQUE INDEX uix_documents_latest_version
    ON documents (version_group_id)
    WHERE is_latest_version = TRUE;

-- Fast lookup by owner
CREATE INDEX ix_documents_owner_id    ON documents (owner_id);
CREATE INDEX ix_documents_group       ON documents (version_group_id);
CREATE INDEX ix_documents_status      ON documents (review_status);
CREATE INDEX ix_documents_expiry      ON documents (expiry_date) WHERE expiry_date IS NOT NULL;
CREATE INDEX ix_documents_renewal     ON documents (renewal_date) WHERE renewal_date IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 3. Document fragments
--    One row per page (PDF) or paragraph (TXT).
--    ID kept as TEXT to preserve the existing "{doc_id}-{index}" format.
-- ---------------------------------------------------------------------------

CREATE TABLE document_fragments (
    id          TEXT        PRIMARY KEY,            -- e.g. "3fa85f64-...-0"
    document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page        INT         NOT NULL,
    text        TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_fragments_document ON document_fragments (document_id, page);


-- ---------------------------------------------------------------------------
-- 4. Document embeddings  (pgvector)
--    One row per fragment; stores the dense vector alongside provenance.
--    Currently 128-dim (local hash-projection); upgrade to 1536 for OpenAI
--    text-embedding-3-small without changing the API endpoints.
-- ---------------------------------------------------------------------------

CREATE TABLE document_embeddings (
    fragment_id TEXT        PRIMARY KEY REFERENCES document_fragments(id) ON DELETE CASCADE,
    document_id UUID        NOT NULL    REFERENCES documents(id) ON DELETE CASCADE,
    page        INT         NOT NULL,
    text        TEXT        NOT NULL,
    embedding   vector(128),             -- swap to vector(1536) for OpenAI embeddings
    provider    TEXT        NOT NULL DEFAULT 'local',
    dim         INT         NOT NULL DEFAULT 128,
    indexed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Approximate nearest-neighbour index (IVFFlat).
-- Tune `lists` ~ sqrt(number of rows); rebuild after bulk loads.
CREATE INDEX ix_embeddings_ivfflat
    ON document_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Exact cosine search index (HNSW) — better recall, higher build cost.
-- Use instead of IVFFlat when the embedding table is < ~1 M rows.
-- CREATE INDEX ix_embeddings_hnsw
--     ON document_embeddings
--     USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

CREATE INDEX ix_embeddings_document ON document_embeddings (document_id);


-- ---------------------------------------------------------------------------
-- 5. Document shares
--    Normalised from the current shared_with list[] on DocumentDetail.
-- ---------------------------------------------------------------------------

CREATE TABLE document_shares (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    shared_with_email   TEXT        NOT NULL,
    shared_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_id, shared_with_email)
);

CREATE INDEX ix_shares_document ON document_shares (document_id);


-- ---------------------------------------------------------------------------
-- 6. Comments
--    Normalised from the current comments list[] on DocumentDetail.
-- ---------------------------------------------------------------------------

CREATE TABLE comments (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    author      TEXT        NOT NULL,   -- email or display name
    body        TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_comments_document ON comments (document_id, created_at DESC);


-- ---------------------------------------------------------------------------
-- 7. Activity events
--    Normalised from the current activity list[] on DocumentDetail.
--    Types: upload | question | retrieval | compare | share | comment |
--           status | metadata | version
-- ---------------------------------------------------------------------------

CREATE TABLE activity_events (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    type        TEXT        NOT NULL,
    label       TEXT        NOT NULL,
    detail      TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_activity_document ON activity_events (document_id, created_at DESC);
CREATE INDEX ix_activity_type     ON activity_events (type);


-- ---------------------------------------------------------------------------
-- 8. Chats and messages
--    Persistent multi-turn conversation sessions per document.
--    The frontend currently stores chat history in component state only;
--    this table is the migration target for durable conversation history.
-- ---------------------------------------------------------------------------

CREATE TABLE chats (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_chats_document ON chats (document_id);
CREATE INDEX ix_chats_user     ON chats (user_id);

CREATE TABLE messages (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id    UUID        NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT        NOT NULL,
    citations  JSONB       NOT NULL DEFAULT '[]',  -- list[DocumentFragment]
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_messages_chat ON messages (chat_id, created_at ASC);


-- =============================================================================
-- Useful queries
-- =============================================================================

-- Top-k semantic search (pgvector cosine distance)
-- Replace $query_vec with the query embedding (same dim as stored vectors).
--
--   SELECT
--       de.fragment_id,
--       de.page,
--       de.text,
--       1 - (de.embedding <=> $query_vec::vector) AS score
--   FROM   document_embeddings de
--   WHERE  de.document_id = $doc_id
--   ORDER  BY de.embedding <=> $query_vec::vector
--   LIMIT  $top_k;


-- Portfolio dashboard (mirrors GET /dashboard)
--
--   SELECT
--       COUNT(*)                                             AS total_documents,
--       COUNT(*) FILTER (WHERE overall_score < 60)          AS high_risk_documents,
--       ROUND(AVG(overall_score))                           AS average_score,
--       COUNT(*) FILTER (WHERE review_status != 'approved') AS pending_review_documents,
--       COUNT(*) FILTER (WHERE review_status = 'approved')  AS approved_documents
--   FROM documents
--   WHERE is_latest_version = TRUE;


-- Documents expiring within 30 days (mirrors GET /deadlines)
--
--   SELECT id, filename, expiry_date,
--          (expiry_date - CURRENT_DATE) AS days_remaining
--   FROM   documents
--   WHERE  is_latest_version = TRUE
--     AND  expiry_date IS NOT NULL
--     AND  expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
--   ORDER  BY expiry_date ASC;
