# Contributing to LuminaClause

LuminaClause is a local-first AI contract review workspace. Contributions should keep the product stable, demoable, and easy to understand for portfolio/recruiter review.

## Working principles

- Keep the local MVP working without paid cloud services.
- Prefer small, focused commits.
- Update README/docs when a user-visible feature changes.
- Keep the local provider as the default analysis path.
- Do not require Claude/OpenAI/Azure keys unless the feature is explicitly optional.
- Preserve citations/source fragments in AI-style answers.
- Avoid committing generated local files unless they are intentionally part of the repo.

## Local setup

Fast path on Windows:

```powershell
.\scripts\check-local.cmd
.\scriptsootstrap.cmd
.\scriptsun-local.cmd
```

Manual backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scriptsctivate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Manual frontend:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

## Validation before commit

Frontend build:

```powershell
cd frontend
npm.cmd run build
cd ..
git checkout -- frontend/next-env.d.ts
```

Backend tests on Windows:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TMP="C:\Projects\AI-Documents-Chat\.tmp"
$env:TEMP="C:\Projects\AI-Documents-Chat\.tmp"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp="C:\Projects\AI-Documents-Chat\.tmp\pytest"
Remove-Item .tmp -Recurse -Force
```

Expected result:

```text
all tests passed
frontend build completed successfully
git status shows a clean tree after commit
```

## Commit style

Use clear conventional-style messages:

```text
feat: add document retrieval panel
fix: stabilize frontend api fallback
docs: update deployment guide
test: cover upload validation
chore: add docker runtime config
```

## Files to treat carefully

- `frontend/next-env.d.ts` may change after local builds. Usually restore it before committing.
- `backend/data/` and upload artifacts should remain local runtime data.
- `.env` and `.env.local` should not contain real secrets.
- Keep `.env.example` files safe and documentation-friendly.

## AI provider changes

When adding Claude/OpenAI/Azure support:

1. Keep `ANALYSIS_PROVIDER=local` as the default.
2. Add provider-specific keys as optional environment variables.
3. Fail gracefully if a selected provider has no API key.
4. Use retrieved source context instead of sending entire documents by default.
5. Document privacy and cost implications.
6. Add tests proving local mode still works without cloud credentials.

## Documentation checklist

When a change affects product behavior, update at least one of:

- `README.md`
- `docs/api.md`
- `docs/architecture.md`
- `docs/portfolio-summary.md`
- `docs/release-checklist.md`
- `CLAUDE.md`
- `docs/claude-handoff.md`

## Good stopping point

Before ending work:

```powershell
git status
```

Ideal output:

```text
nothing to commit, working tree clean
```
