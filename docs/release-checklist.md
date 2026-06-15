# LuminaClause local MVP release checklist

## Status

Local-first full-stack MVP — cloud providers optional and key-guarded, PostgreSQL CRUD implemented, deployment guide ready.

## Verified capabilities

### Core product

- Landing page
- Local login/register with JWT-ready auth (PBKDF2-SHA256 passwords, HS256 tokens)
- Ownership-aware uploads
- PDF/TXT upload and bulk upload
- Drag & drop upload with progress
- Upload validation: file type, empty file, 5 MB limit, safe filenames
- AI-style summary (local + cloud providers)
- Document Q&A with citations and streaming SSE answers
- Conversation history
- Fragment search
- Risk scoring
- Missing clause detection
- Suggested safer wording
- Metadata and deadlines
- Review comments and statuses
- Contract comparison
- Version upload
- Markdown answers and reports
- Report download
- Archive/delete workflow

### Architecture and infrastructure

- `AnalysisProvider` interface — `LocalProvider` (default), `ClaudeProvider` (fully wired, `ANTHROPIC_API_KEY`), `OpenAIProvider` (fully wired, `OPENAI_API_KEY`)
- `DocumentRepository` abstraction — `JsonDocumentRepository` (default), `PostgresDocumentRepository` (create/list/get/delete wired; 7 operations stubbed)
- JWT auth endpoints: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- Embeddings-ready vector retrieval layer (hash-projection, 128-dim, `/vector-search`)
- Operational endpoints: `GET /health`, `GET /metrics`, `GET /provider`, `GET /runtime`
- Dashboard AI mode badge and storage backend badge
- Runtime data gitignored (`documents.json`, `users.json`, `embeddings.json`, `uploads/`)
- Docker Compose runtime (frontend + backend + PostgreSQL + pgvector)
- Backend CI (GitHub Actions — 263 tests, 9 skipped)
- Frontend build CI (GitHub Actions — `next build`)
- Swagger/OpenAPI docs at `/docs`
- API reference, architecture notes, database schema, deployment guide, portfolio summary

## Local validation

Backend tests:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TMP="C:\Projects\AI-Documents-Chat\.tmp"
$env:TEMP="C:\Projects\AI-Documents-Chat\.tmp"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp="C:\Projects\AI-Documents-Chat\.tmp\pytest"
Remove-Item .tmp -Recurse -Force
```

Frontend build:

```powershell
cd frontend
npm.cmd run build
cd ..
git checkout -- frontend/next-env.d.ts
```

Docker:

```powershell
docker compose up --build
```

## Demo flow

1. Login/register locally (JWT issued, stored in localStorage, validated on reload).
2. Upload sample contracts.
3. Ask a document question; watch the answer stream in with citations.
4. Inspect risks, suggestions, and missing clause flags.
5. Add metadata, comment, and status.
6. Compare contracts.
7. Generate and download a report.
8. Archive a document.
9. Show AI mode badge and storage backend badge in the sidebar.

## Known limits (intentionally deferred)

- **Auth** — `AUTH_SECRET` is a dev placeholder when unset; `auth_store.py` uses `data/users.json` (not a production database). Migration path: set a real secret, swap for a PostgreSQL-backed store, add HTTPS.
- **Storage** — default is local JSON (`STORAGE_BACKEND=json`). PostgreSQL create/list/get/delete are wired; the 7 remaining operations raise `NotImplementedError` at call time.
- **AI** — `LocalProvider` is default (no key, no network calls). Activate Claude or OpenAI via `backend/.env`.
- **Embeddings** — local hash-projection (128-dim, non-semantic). Migration to real embeddings (OpenAI, sentence-transformers) and pgvector is documented in `docs/architecture.md`.
- **Files** — originals stored in `data/uploads/` locally. Object storage (S3/Azure Blob) not yet wired.
- **Deployment** — no public URL yet. Render/Vercel deployment guide in `docs/deployment.md`.

## Next milestone

Complete the PostgreSQL repository — implement the 7 remaining operations in `store_pg.py` and replace the corresponding stubs in `PostgresDocumentRepository`. See the step-by-step guide in `docs/architecture.md#completing-the-postgresql-migration`.
