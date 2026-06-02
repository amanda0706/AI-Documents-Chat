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

## Current recommended next step

Before adding real Claude/OpenAI calls, add a clean **cloud AI provider adapter seam**:

1. Define provider configuration keys in `.env.example` and `backend/.env.example`.
2. Add a placeholder Claude/OpenAI provider class that is not active unless configured.
3. Keep local provider as default.
4. Document how to enable cloud AI later.
5. Add tests that local provider remains default when no key exists.

Do not break local-first operation.

## Product direction

The next serious production upgrades are:

- real auth/workspaces,
- PostgreSQL persistence,
- pgvector embeddings,
- object storage,
- Claude/OpenAI/Azure provider,
- deployment once a free/acceptable hosting path is chosen.
