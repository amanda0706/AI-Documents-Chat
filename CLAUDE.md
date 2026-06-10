# Claude handoff: LuminaClause

You are working on **LuminaClause**, a local-first AI contract/document review workspace.

## Product goal

LuminaClause helps users upload contracts, inspect risky clauses, ask document-grounded questions, compare versions, export review reports, and move documents through a lightweight review workflow.

This is a portfolio-grade MVP. Prioritize stability, readable architecture, and recruiter-facing clarity over speculative complexity.

## Current stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Python
- Current persistence: local JSON/filesystem
- Current AI mode: deterministic local provider, no cloud AI key required
- Runtime: local scripts and Docker Compose
- CI: GitHub Actions for backend tests and frontend build

## Important current state

The app is intentionally **local-first** right now. Do not assume OpenAI, Claude, Azure, Supabase, or cloud credentials exist.

Already implemented:

- landing page
- local auth/session mock
- PDF/TXT upload
- upload validation and safe filenames
- document dashboard
- document workspace
- AI-style local summary
- risk detection and scoring
- suggestions and missing clause detection
- grounded Q&A with citations
- streaming answers (SSE)
- local semantic retrieval endpoint (embeddings-ready, 128-dim hash-projection)
- chat history
- metadata/deadline workflow
- comments/share/review status
- document versioning
- document comparison
- markdown report export
- archive/delete workflow
- `/health` and `/metrics`
- Swagger/OpenAPI docs
- Docker Compose
- backend tests (200 passing)
- frontend build workflow
- API docs, architecture docs, database schema plan, release checklist, portfolio summary
- **JWT-ready local auth** (PBKDF2-SHA256 passwords, HS256 JWTs, timing-safe, stdlib-only)
- **document repository abstraction** (`repository.py` — `DocumentRepository` Protocol, `JsonDocumentRepository`, `PostgresDocumentRepository` placeholder, `STORAGE_BACKEND` env var)

## How to run locally on Windows

From repository root:

```powershell
.\scriptsootstrap.cmd
.\scriptsun-local.cmd
```

Or manually:

```powershell
cd backend
.\.venv\Scriptsctivate
uvicorn app.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm.cmd run dev
```

Frontend usually runs on `http://localhost:3000`. If the port is busy, Next.js may choose another port.
Backend docs: `http://localhost:8000/docs`.

## Validation commands

Frontend:

```powershell
cd frontend
npm.cmd run build
cd ..
git checkout -- frontend/next-env.d.ts
```

Backend tests on Windows, avoiding temp permission problems:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TMP="C:\Projects\AI-Documents-Chat\.tmp"
$env:TEMP="C:\Projects\AI-Documents-Chat\.tmp"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp="C:\Projects\AI-Documents-Chat\.tmp\pytest"
Remove-Item .tmp -Recurse -Force
```

## Known Windows notes

- `frontend/next-env.d.ts` changes after build. Do not commit it unless intentionally needed. Usually restore it:

```powershell
git checkout -- frontend/next-env.d.ts
```

- Pytest may fail if it uses the default Windows temp directory. Use the `.tmp` command block above.
- If PowerShell shows `>>`, the user is inside an unfinished multiline command. Tell them to press `Ctrl+C`.

## Current state of the AI provider layer

`ClaudeProvider` is **fully implemented** (`anthropic==0.55.0` in `requirements.txt`, 55 backend tests pass, all mocked — no real key needed for tests or local run).

- `ANALYSIS_PROVIDER=local` — default, no key, no network calls, all analysis on-device.
- `ANALYSIS_PROVIDER=claude` — active; sends retrieved fragments to Anthropic Messages API; structured fields (risks, score, suggestions) remain local.
- `ANALYSIS_PROVIDER=openai` — adapter seam ready; SDK calls not yet wired.

`backend/.env` is loaded automatically at startup (`python-dotenv`) and is gitignored. To activate Claude locally:

```powershell
cp backend/.env.example backend/.env
# edit backend/.env:
#   ANALYSIS_PROVIDER=claude
#   ANTHROPIC_API_KEY=sk-ant-...
```

Never commit `backend/.env`. It is covered by `.gitignore:1` (`.env` rule).

**Privacy rule:** when a cloud provider is active, document fragments are sent to a third-party API. Never enable a cloud provider for real sensitive contracts without explicit consent from all relevant parties and a review of the provider's data-handling terms.

## Embeddings layer (implemented)

`backend/app/embeddings.py` provides a RAG-ready vector retrieval layer:

- `local_embed(text)` — deterministic hash-projection, 128-dim unit vector, no external deps.
- `cosine_similarity(a, b)` — dot product of unit vectors.
- `reindex_document(doc)` — embeds all fragments and persists to `data/embeddings.json`.
- `vector_search(query, doc_id, top_k)` — top-k retrieval by cosine similarity.

API endpoints added:
- `POST /embeddings/reindex` — index one or all documents.
- `GET /documents/{id}/embeddings` — list embedding metadata (vectors optional).
- `GET /documents/{id}/vector-search` — semantic retrieval endpoint.

Migration paths to production embeddings and pgvector are documented in
`docs/architecture.md` and inline in `embeddings.py`.

## JWT auth layer (implemented)

`backend/app/auth.py` — stdlib-only JWT + PBKDF2 password hashing (no new pip deps):

- `create_token(user_id, email)` — HS256 JWT, 24-hour expiry, signed with `AUTH_SECRET` env var.
- `decode_token(token)` — validates signature via `hmac.compare_digest`, checks `exp`.
- `hash_password(password)` → `(hash_hex, salt_hex)` — PBKDF2-SHA256, 100 k iterations, 32-byte random salt.
- `verify_password(password, stored_hash, salt_hex)` — timing-safe via `hmac.compare_digest`.

`backend/app/auth_store.py` — JSON user store at `data/users.json`:

- `register_user(email, password)` — case-normalises email, raises `ValueError` on duplicate.
- `authenticate_user(email, password)` — timing-safe: always runs `verify_password` even for unknown emails.
- `get_user_by_id(user_id)` — used by `GET /auth/me`.
- `_public(record)` — strips `password_hash` and `salt` from every response.

API endpoints added to `main.py`:

- `POST /auth/register` — 409 on duplicate email, 422 if password < 6 chars.
- `POST /auth/login` — 401 for both wrong password and unknown email (no enumeration).
- `GET /auth/me` — parses `Authorization: Bearer <token>`, returns `UserPublic` or 401.

Frontend (`dashboard.tsx`):

- Page-load `useEffect` validates stored JWT via `GET /auth/me`; clears expired/tampered tokens.
- `completeAuth()` calls `authRegister`/`authLogin`, stores JWT in `luminaclause:token`.
- Falls back to local email-only session if backend is unavailable.
- Password input added to auth form with Enter key handler.

Tests: `backend/tests/test_auth.py` — 36 tests covering register, login, `/auth/me`, secret leakage.  Full suite: **200 passing**.

`AUTH_SECRET` env var must be set in production to a 256-bit random string. Dev placeholder is used when absent but logs a warning path in architecture docs.

## Document repository abstraction (implemented)

`backend/app/repository.py` — PEP 544 structural Protocol + two implementations:

- `DocumentRepository` — `@runtime_checkable` Protocol covering all 11 document persistence operations.
- `JsonDocumentRepository` — delegates every method to `store.*` at call time; monkeypatching `store.INDEX_FILE` in tests works unchanged.
- `PostgresDocumentRepository` — partial implementation (see below); delegates to `store_pg.*`.
- `get_repository()` — factory driven by `STORAGE_BACKEND` env var (`json` default; `postgres` returns `PostgresDocumentRepository`).

`main.py` changes:
- All document store function imports removed; `UPLOADS_DIR` kept as direct import (temp file handling during upload is not a repository concern).
- `repo = get_repository()` added at module level, parallel to `provider = get_provider()`.
- Every route calls `repo.*` instead of bare `store.*` functions.

Tests: `backend/tests/test_repository.py` — 26 tests covering factory selection, protocol conformance, and full CRUD round-trip.

## PostgreSQL document lifecycle (implemented — first slice)

`backend/app/store_pg.py` — psycopg2-binary implementation of the core document lifecycle:

**Implemented:** `create_document`, `list_documents`, `get_document`, `delete_document`
  - `delete_document` relies on `ON DELETE CASCADE` in `db/schema.sql` to remove fragments, embeddings, shares, comments, and activity automatically.
  - All queries use `%s` parameterised placeholders — no string interpolation.
  - Each operation acquires a connection from `DATABASE_URL`, commits on success, rolls back on error, always closes.

**Intentional stubs (raise `NotImplementedError` with a clear message):**
  `create_document_version`, `list_document_versions`, `add_activity`, `share_document`, `add_comment`, `update_review_status`, `update_metadata`

**Dependencies:** `psycopg2-binary==2.9.12` added to `requirements.txt`.

**Tests:**
- `backend/tests/test_postgres_repository.py` — 48 unit tests (mocked cursor, no Docker required) + 9 integration tests (skipped unless `TEST_DATABASE_URL` is set).
- `backend/conftest.py` — registers `integration` mark so pytest does not emit warnings.
- Unit tests verify parameterised SQL, commit/rollback contract, and delegation from `PostgresDocumentRepository` → `store_pg`.

**Activate locally:**
```bash
# backend/.env (gitignored)
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://luminaclause:luminaclause_dev@localhost:5432/luminaclause
```

**Run integration tests (requires Docker db service):**
```bash
$env:TEST_DATABASE_URL="postgresql://luminaclause:luminaclause_dev@localhost:5432/luminaclause_test"
python -m pytest backend/tests/test_postgres_repository.py -m integration -v
```

Extending the implementation: add a SQL function to `store_pg.py`, replace the `_not_implemented()` stub call in `PostgresDocumentRepository`, add a mock-cursor unit test. JSON-path tests need no changes.

## Current recommended next step

Wire `OpenAIProvider` SDK calls to match the `ClaudeProvider` pattern:

1. Add `openai` to `backend/requirements.txt`.
2. Implement `OpenAIProvider.summarize_document`, `.answer`, `.compare` following the same JSON-structured prompt pattern used in `ClaudeProvider`.
3. Add mocked unit tests (mirror `test_providers.py` Claude tests).
4. Run backend tests and frontend build before committing.

Do not break local-first operation. Do not require any API key for tests or CI.

## Product direction

The next serious production upgrades are:

- OpenAI provider SDK calls (mirrors ClaudeProvider — seam is already in place),
- complete the PostgreSQL repository (implement remaining 7 operations in `store_pg.py`),
- swap `local_embed` for real sentence embeddings (OpenAI, sentence-transformers) — no endpoint changes needed,
- real auth/workspaces,
- object storage,
- deployment once a free/acceptable hosting path is chosen.
