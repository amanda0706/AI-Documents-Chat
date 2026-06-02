# LuminaClause detailed handoff

## What this repo is

LuminaClause is an AI-style contract/document assistant built as a practical SaaS-like portfolio project. It currently works without cloud AI so the full workflow can be tested locally and reliably.

The project should feel like a contract review cockpit: upload a document, inspect extracted clauses, ask grounded questions, compare versions, track status, comment, export a report, and see operational readiness through API endpoints.

## Repository map

```text
backend/
  app/
    main.py          FastAPI routes
    models.py        Pydantic contracts
    providers.py     analysis provider seam
    services.py      business/report/comparison logic
    store.py         local JSON persistence
    analyzer.py      local scoring/retrieval helpers
    deadlines.py     contract lifecycle helpers
    extraction.py    PDF/TXT extraction
  tests/             backend tests
frontend/
  src/app/           Next.js app entry
  src/components/    dashboard/workspace UI
  src/lib/           API client + TypeScript types
docs/
  api.md
  architecture.md
  deployment.md
  portfolio-summary.md
  release-checklist.md
scripts/
  bootstrap/run/check local helpers
```

## Design constraints

- Preserve local demo reliability.
- Avoid requiring paid services by default.
- Keep new features visible in README/docs.
- Prefer small commits with clear messages.
- Run frontend build and backend tests before commits.

## API landmarks

- `GET /health`
- `GET /metrics`
- `GET /dashboard`
- `GET /documents`
- `POST /documents/upload`
- `POST /documents/bulk-upload`
- `GET /documents/{id}/retrieval`
- `POST /documents/{id}/ask`
- `GET /documents/{id}/report`
- `POST /compare`
- `DELETE /documents/{id}`

## Current AI/provider model

The app has a local deterministic provider. This gives predictable summaries, risks, suggestions, Q&A, and comparison behavior without API keys.

When adding Claude/OpenAI later:

- do not remove the local provider,
- keep `ANALYSIS_PROVIDER=local` as default,
- fail gracefully if a cloud provider is selected but no key exists,
- keep citations/source fragments central to the UX,
- avoid sending real sensitive contracts to third-party APIs without explicit user consent and documentation.

## Suggested Claude-ready implementation plan

### Step 1: provider configuration

Add environment examples:

```env
ANALYSIS_PROVIDER=local
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
AI_MODEL=
```

### Step 2: provider classes

Add provider adapters behind the existing provider interface. Keep imports optional if possible so the app still runs without cloud SDKs.

### Step 3: retrieval first

Use the existing local retrieval endpoint as the context builder. Cloud AI should answer from retrieved context, not from the whole document blindly.

### Step 4: tests

Add tests proving:

- default provider is local,
- missing cloud key gives a controlled error or falls back safely,
- `/ask` still returns citations.

### Step 5: docs

Update README, `docs/api.md`, and `docs/architecture.md` with provider activation instructions.

## Useful demo commands

```powershell
cd "C:\Projects\AI-Documents-Chat"
.\scriptsun-local.cmd
```

If a service gets stuck, stop with `Ctrl+C`, then check ports:

```powershell
netstat -ano | findstr :3000
netstat -ano | findstr :8000
```

## Git hygiene

Before stopping work:

```powershell
git status
```

A good stopping state is:

```text
nothing to commit, working tree clean
```
