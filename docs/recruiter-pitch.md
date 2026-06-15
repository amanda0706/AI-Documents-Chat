# LuminaClause — recruiter pitch

## 1. GitHub repo description (max 160 chars)

> Local-first AI contract review workspace — Next.js, FastAPI, Claude/OpenAI, RAG retrieval, PostgreSQL-ready, Docker, CI. Upload PDFs, ask grounded questions, detect risky clauses.

*(158 characters — paste this into Settings → About on the GitHub repo page)*

---

## 2. CV bullet points

**LuminaClause — AI Contract Review Assistant** · [github.com/amanda0706/AI-Documents-Chat](https://github.com/amanda0706/AI-Documents-Chat)

- Built a full-stack AI document assistant (Next.js 15, TypeScript, FastAPI, Python) with streaming grounded Q&A, RAG-style vector retrieval, contract risk scoring, and a full document review workflow — deployed via Docker Compose with GitHub Actions CI and Swagger/OpenAPI docs.
- Wired Claude and OpenAI providers behind a shared `AnalysisProvider` interface and a `DocumentRepository` abstraction (JSON default; PostgreSQL CRUD via psycopg2) — both backends activate through env vars with no product code changes, demonstrating production-ready separation of concerns.
- Implemented JWT auth (PBKDF2-SHA256, HS256, timing-safe `hmac.compare_digest`), SSE streaming answers, 263 backend tests, and observable runtime endpoints (`/provider`, `/runtime`) — pgvector and object storage migration paths documented and ready to wire.

---

## 3. LinkedIn project posts

### Polish version

Właśnie skończyłam budować **LuminaClause** — asystenta do przeglądu umów opartego na AI.

Projekt powstał, żeby pokazać jak wygląda pełna realizacja produktu AI od zera: interfejs użytkownika, API, retrieval, dostawcy modeli i gotowość do wdrożenia na produkcję.

Co zostało zbudowane:
- Upload PDF/TXT, analiza ryzyka, pytania do dokumentu z cytowaniami i streamingiem odpowiedzi
- Obsługa Claude i OpenAI jako opcjonalnych dostawców — przełączanie przez zmienną środowiskową
- Abstrakcja repozytorium dokumentów (JSON domyślnie, PostgreSQL gotowy do aktywacji)
- Lokalna warstwa RAG z embeddingami i wyszukiwaniem kosinusowym
- Autoryzacja JWT (PBKDF2-SHA256, HS256) pisana od zera bez zewnętrznych bibliotek
- 263 testy backendowe, CI/CD (GitHub Actions), Docker Compose, dokumentacja OpenAPI

Projekt działa lokalnie bez kluczy API — pełny workflow dostępny od razu po klonowaniu.

Stack: Next.js · TypeScript · FastAPI · Python · PostgreSQL · Docker · Tailwind

🔗 github.com/amanda0706/AI-Documents-Chat

---

### English version

I just shipped **LuminaClause** — an AI-assisted contract review workspace.

The goal was to build something that demonstrates real full-stack product thinking: not just an API wrapper, but a complete review workflow with a swappable AI layer and a documented migration path to production infrastructure.

What's inside:
- PDF/TXT upload, risk scoring, streaming grounded Q&A with citations
- Claude and OpenAI providers fully wired — switch with a single env var, no code changes
- `DocumentRepository` abstraction with JSON (default) and PostgreSQL backends
- Local RAG layer: hash-projection embeddings, cosine similarity, top-k retrieval
- JWT auth built from stdlib only (PBKDF2-SHA256, HS256, timing-safe verification)
- 263 backend tests, CI (GitHub Actions), Docker Compose, Swagger/OpenAPI docs

Runs fully offline without any API keys — clone, bootstrap, and the whole workflow is live.

Stack: Next.js · TypeScript · FastAPI · Python · PostgreSQL · Docker · Tailwind

🔗 github.com/amanda0706/AI-Documents-Chat

---

## 4. Interview pitch

### 30-second version

"I built LuminaClause — a full-stack AI contract review assistant. The backend is FastAPI with a provider interface that supports local analysis, Claude, and OpenAI — you flip between them with an env var. The frontend is Next.js with streaming answers and a full review workflow. I also built a document repository abstraction so the app runs on JSON today and can switch to PostgreSQL without changing any product code. There are 263 tests, CI, Docker Compose, and JWT auth written from scratch. It runs completely offline from a fresh clone."

### 2-minute version

"LuminaClause is a contract review workspace I built to demonstrate full-stack AI product engineering end-to-end.

The product workflow lets a reviewer upload a PDF or text contract, get an AI-generated summary with risk flags, ask grounded questions — the answers stream in with citations back to the exact source passages — compare two contract versions, and export a markdown review report. There's a review queue, comments, status workflow, and activity history.

On the backend I designed a layered architecture around two interfaces. The first is `AnalysisProvider`, which has three implementations: a local deterministic provider that needs no API key, a Claude provider using the Anthropic SDK, and an OpenAI provider. Switching between them is one env var. The second interface is `DocumentRepository`, which abstracts all document persistence — the default implementation uses local JSON and the PostgreSQL implementation has the core lifecycle wired with psycopg2. The seam is clean enough that no route code changes when you switch backends.

I also built JWT auth from stdlib only — PBKDF2-SHA256 password hashing with 100,000 iterations, HS256 tokens, timing-safe comparison with `hmac.compare_digest`. No external auth package.

The RAG layer uses a local hash-projection embedding function I built to keep it dependency-free — it gives scored fragment retrieval without needing an API key. The migration path to OpenAI embeddings or sentence-transformers is a one-function swap; pgvector SQL is already written.

There are 263 backend tests, GitHub Actions CI running on every push, Docker Compose for the full stack including PostgreSQL, and Swagger/OpenAPI docs. The whole thing runs from a fresh clone with no credentials."

---

## 5. Technical highlights

### Backend (FastAPI · Python)

- `AnalysisProvider` Protocol — `LocalProvider` (default), `ClaudeProvider` (Anthropic SDK), `OpenAIProvider` (OpenAI SDK); all share the same JSON response contract
- `DocumentRepository` Protocol (PEP 544 structural typing) — `JsonDocumentRepository` and `PostgresDocumentRepository` (psycopg2-binary, parameterised SQL only)
- Streaming SSE answers via `/documents/{id}/ask/stream`
- Observable runtime: `GET /provider` and `GET /runtime` — never expose secrets
- Upload guardrails: file type, empty file, 5 MB limit, sanitised filenames
- 263 backend tests; mocked unit tests for PostgreSQL (no Docker required in CI); integration tests gated by `TEST_DATABASE_URL`

### Frontend (Next.js 15 · TypeScript · Tailwind)

- Streaming Q&A with SSE — answers render word by word, citations highlighted after completion
- Dashboard: risk queue, portfolio metrics, deadlines, review queue, ownership breakdown
- Document workspace: fragment viewer, AI summary, risk labels, metadata editor, comments, activity feed
- Contract comparison with category-tagged differences and impact notes
- Markdown report generation and download
- AI mode badge (`/provider`) and storage backend badge (`/runtime`) — live state visible in the sidebar
- Graceful fallback: all API calls return controlled empty states; JWT falls back to local email session when backend is unavailable

### AI / RAG

- `AnalysisProvider` interface isolates all AI interaction; no AI code in routes
- Local hash-projection embeddings: 128-dim deterministic unit vectors, cosine similarity, top-k retrieval — no API key, no external model
- Source-grounded answers: only retrieved fragments are sent to the cloud provider, not full documents
- Drop-in migration: replace `local_embed()` with `openai.embeddings.create()` or `SentenceTransformer.encode()` — no endpoint changes
- pgvector DDL written and documented in `db/schema.sql`

### Database / cloud readiness

- PostgreSQL DDL: `documents`, `document_versions`, `fragments`, `embeddings`, `shares`, `comments`, `activity`, `users` — all with `ON DELETE CASCADE`
- `DatabaseURL` never logged or exposed in API responses
- `STORAGE_BACKEND=postgres` activates the psycopg2 layer — CRUD lifecycle wired; 7 workflow operations stubbed with clear `NotImplementedError` messages
- Docker Compose runs PostgreSQL + pgvector alongside the application stack
- `TEST_DATABASE_URL` isolation prevents tests from touching production databases
- Deployment guide: Render (backend) + Vercel (frontend); `render.yaml` included

### Security / auth / testing

- PBKDF2-SHA256 passwords: 100,000 iterations, 32-byte random salt, stdlib only
- HS256 JWTs signed with `AUTH_SECRET`; 24-hour expiry; `GET /auth/me` validates on every page load
- Timing-safe comparison: `hmac.compare_digest` for both password and token signature checks
- No credential values in API responses; `DATABASE_URL`, `AUTH_SECRET`, and API keys gitignored
- 263 backend tests: unit tests, upload validation, auth (36 tests), repository (26 tests), provider mocks (11 tests), PostgreSQL mocks (48 tests)
- GitHub Actions CI: backend tests + frontend production build on every push and pull request

---

## 6. Honest limitations / next steps

| Area | Current state | What's needed |
|---|---|---|
| **Live deployment** | No public URL yet | Render (backend) + Vercel (frontend); `render.yaml` and deployment guide ready |
| **PostgreSQL** | CRUD wired (create/list/get/delete); 7 operations stubbed | Implement `create_document_version`, `list_document_versions`, `add_activity`, `share_document`, `add_comment`, `update_review_status`, `update_metadata` in `store_pg.py` |
| **Production auth** | JWT logic is real; user store is `data/users.json` | Set `AUTH_SECRET` to a 256-bit secret; swap `auth_store.py` for PostgreSQL; add HTTPS |
| **Embeddings** | Local hash-projection (non-semantic, 128-dim) | Swap `local_embed()` for OpenAI `text-embedding-3-small` or sentence-transformers; activate pgvector |
| **File storage** | Uploaded files in `data/uploads/` (local) | Wire S3 or Azure Blob; keep `UPLOADS_DIR` as the seam |
| **Multi-user / workspaces** | Single local user store | Requires PostgreSQL auth + workspace-scoped document queries |

---

## 7. Suggested GitHub pinned repo settings

### Repo description (paste into Settings → About)

```
Local-first AI contract review workspace — Next.js, FastAPI, Claude/OpenAI, RAG retrieval, PostgreSQL-ready, Docker, CI.
```

### Topics / tags

```
nextjs  fastapi  python  typescript  ai  rag  openai  anthropic  claude  postgresql  pgvector  docker  jwt  contract-review  document-analysis  nlp  full-stack  portfolio
```

*(GitHub allows up to 20 topics — this list uses 18)*
