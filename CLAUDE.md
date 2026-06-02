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
- local semantic retrieval endpoint
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
- backend tests
- frontend build workflow
- API docs, architecture docs, release checklist, portfolio summary

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

**Privacy rule:** when a cloud provider is active, document fragments are sent to a third-party API. Never enable a cloud provider for real sensitive contracts without explicit consent from all relevant parties and a review of the provider's data-handling terms.

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
- real auth/workspaces,
- PostgreSQL persistence,
- pgvector embeddings,
- object storage,
- deployment once a free/acceptable hosting path is chosen.
