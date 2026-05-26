# LuminaClause local MVP release checklist

## Status

Local-first full-stack MVP before cloud deployment.

## Verified capabilities

- Landing page
- Local login/register mock
- Ownership-aware uploads
- PDF/TXT upload and bulk upload
- Drag & drop upload with progress
- Upload validation: file type, empty file, 5 MB limit, safe filenames
- AI-style summary
- Document Q&A with citations
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
- Docker Compose runtime
- Backend CI
- Frontend build CI
- API docs

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

1. Login/register locally.
2. Upload sample contracts.
3. Ask a document question.
4. Inspect citations and chat history.
5. Review risks and suggestions.
6. Add metadata/comment/status.
7. Compare contracts.
8. Generate report.
9. Archive a document.

## Known local MVP limits

- Auth is local mock.
- Storage is JSON/filesystem.
- AI provider is local deterministic logic.
- No pgvector yet.
- No public deployment yet.

## Next milestone

Cloud deployment + real auth + PostgreSQL/pgvector + OpenAI/Azure OpenAI provider.
