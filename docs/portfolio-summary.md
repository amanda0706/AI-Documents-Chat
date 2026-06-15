# LuminaClause portfolio summary

## One-line pitch

LuminaClause is a local-first AI document review workspace for contract upload, grounded Q&A, risk analysis, comparison, review workflow, and production-ready API operations — with optional Claude and OpenAI backends and a clear migration path to PostgreSQL and cloud deployment.

## CV version

**LuminaClause — AI Contract Review Assistant**
Built a full-stack document assistant using Next.js, TypeScript, FastAPI, and Python. The app supports PDF/TXT upload, local document analysis, streaming grounded Q&A with citations, semantic retrieval, contract comparison, risk scoring, review workflow, JWT-ready local auth, markdown reports, Docker runtime, API documentation, CI checks, and operational health/metrics endpoints. Optional Claude and OpenAI providers are fully wired and key-guarded; a `DocumentRepository` abstraction with JSON and PostgreSQL backends demonstrates a real migration path to cloud persistence.

## Recruiter-friendly summary

This project demonstrates how I design and ship an AI-style SaaS product end-to-end: user experience, backend APIs, local persistence, analysis abstraction, testing, documentation, and deployment readiness. The current MVP runs without cloud AI so the workflow is reliable and testable from a fresh clone. Cloud providers (Claude, OpenAI), PostgreSQL storage, and pgvector are ready to activate through environment variables — the product workflow does not change.

## Engineering highlights

- Built a polished Next.js dashboard with upload, document workspace, streaming Q&A, comparison, suggestions, metadata, review status, comments, and archive flows.
- Designed FastAPI endpoints for document lifecycle, chat, streaming SSE, retrieval, reports, deadlines, metrics, and review collaboration.
- Wired `ClaudeProvider` (Anthropic SDK) and `OpenAIProvider` (OpenAI SDK) behind a shared `AnalysisProvider` Protocol; local provider remains the default — no key required.
- Implemented `DocumentRepository` abstraction (PEP 544 structural Protocol) with `JsonDocumentRepository` (default) and `PostgresDocumentRepository` (psycopg2; create/list/get/delete wired).
- Added JWT-ready local auth: PBKDF2-SHA256 passwords, HS256 tokens, timing-safe verification via `hmac.compare_digest`, `GET /auth/me` token validation on every page load.
- Implemented a RAG-ready local retrieval layer (hash-projection embeddings, cosine similarity, top-k vector search) with a documented drop-in migration path to OpenAI embeddings and pgvector.
- Added observable runtime status endpoints (`GET /provider`, `GET /runtime`) that surface AI and storage configuration to the dashboard without exposing secrets.
- Added validation for uploads: file type, empty file, 5 MB limit, safe filenames.
- Covered 263 backend tests (unit + mocked integration); frontend production build verified on every push via GitHub Actions.

## What is implemented vs. intentionally future

### Implemented now

| Area | What works today |
|---|---|
| AI providers | `LocalProvider` (default), `ClaudeProvider` (Anthropic SDK), `OpenAIProvider` (OpenAI SDK) — all fully wired |
| Storage | JSON file store (default); PostgreSQL CRUD lifecycle (`create_document`, `list_documents`, `get_document`, `delete_document`) |
| Auth | JWT-ready local auth (PBKDF2, HS256, `hmac.compare_digest`); stored in `data/users.json` |
| Retrieval | Local hash-projection embeddings, cosine similarity, `/vector-search` endpoint |
| Streaming | SSE streaming answers via `/documents/{id}/ask/stream` |
| Observability | `/health`, `/metrics`, `/provider`, `/runtime` |
| Frontend | Dashboard, workspace, comparison, upload, review workflow, badges for AI mode and storage backend |
| CI / Docker | GitHub Actions (backend tests + frontend build), Docker Compose (frontend + backend + PostgreSQL) |

### Intentionally future (not yet implemented)

| Area | Status |
|---|---|
| PostgreSQL — remaining 7 operations | `create_document_version`, `list_document_versions`, `add_activity`, `share_document`, `add_comment`, `update_review_status`, `update_metadata` are stubs |
| Production auth | `AUTH_SECRET` must be set to a real secret; `auth_store.py` must be swapped for a PostgreSQL-backed store; HTTPS required |
| Real cloud storage | Original files live in `data/uploads/` (local); S3/Azure Blob not yet wired |
| pgvector embeddings | Local hash-projection today; migration SQL documented; no live pgvector query yet |
| Hosted deployment | No live public URL yet; Render/Vercel deployment guide documented |

## Demo story

1. Open the landing page and explain the product: contract review assistant for faster first-pass review.
2. Log in with any email to enter the local workspace (local auth mock with JWT backend).
3. Upload a sample `.txt` or `.pdf` contract.
4. Show the dashboard: risk score, review queue, deadlines, ownership, and portfolio metrics.
5. Point to the AI mode badge (`AI mode: Local`) and storage backend badge (`Storage: JSON`) — explain both are switchable via env vars.
6. Open the document workspace and show extracted fragments, AI summary, risks, metadata, and comments.
7. Ask a contract question; show that the answer streams in and includes citations.
8. Run semantic retrieval to show RAG-style context search.
9. Compare two documents and show the difference summary.
10. Generate a markdown report.
11. Mention Docker, tests, CI, API docs, `/health`, `/metrics`, `/provider`, `/runtime`, and the cloud AI / PostgreSQL migration path.

## What makes this portfolio-ready

- Real product framing around a concrete workflow — not a generic chatbot.
- Streaming AI interaction with citations, markdown-rendered answers, chat history, and report preview.
- Full-stack delivery: polished Next.js UI + validated FastAPI backend.
- Two cloud AI providers fully wired and swappable without product changes.
- `DocumentRepository` abstraction with JSON and partial PostgreSQL implementations demonstrates real migration thinking.
- JWT-ready auth with real cryptography (PBKDF2, HMAC) — not just a session cookie.
- 263 backend tests, CI, Docker Compose, Swagger/OpenAPI, API reference, architecture notes, database schema, deployment guide.
- Fresh-clone bootstrap scripts; runtime data gitignored so the repo is clean.
