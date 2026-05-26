# LuminaClause deployment guide

This guide deploys the current local-first MVP without cloud AI.

Recommended first deployment:

- Backend: Render Docker web service
- Frontend: Vercel Next.js project
- Persistence: local Render service filesystem for demo use only

For a production version, move persistence to PostgreSQL + object storage before storing real customer documents.

## 1. Deploy backend to Render

Render can read the repository-level `render.yaml` Blueprint.

1. Open Render.
2. Create a new Blueprint from the GitHub repository.
3. Select the repository: `amanda0706/AI-Documents-Chat`.
4. Render should detect `render.yaml`.
5. Confirm the `luminaclause-api` web service.
6. Wait for deploy to finish.
7. Open:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
https://YOUR-RENDER-SERVICE.onrender.com/metrics
https://YOUR-RENDER-SERVICE.onrender.com/docs
```

Expected health response:

```json
{ "status": "ok" }
```

## 2. Deploy frontend to Vercel

1. Open Vercel.
2. Import the same GitHub repository.
3. Set the project root directory to:

```text
frontend
```

4. Add environment variables for Production and Preview:

```env
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-SERVICE.onrender.com
INTERNAL_API_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

5. Deploy.

## 3. Verify production smoke test

Open the Vercel URL and check:

- landing page loads,
- login with any email works,
- dashboard loads without framework error overlay,
- upload accepts `.txt` or `.pdf`,
- document Q&A returns answer with citations,
- semantic retrieval returns source fragments,
- compare flow works when at least two documents exist,
- backend `/health`, `/metrics`, and `/docs` are reachable.

## 4. Known demo limitation

The Render backend currently uses local JSON/filesystem persistence. That is fine for a portfolio MVP, but data can disappear when the service is rebuilt or moved. Production persistence should use PostgreSQL, pgvector, and object storage.

## 5. Production upgrade path

- Add managed PostgreSQL.
- Move document metadata and chat history into database tables.
- Move uploaded files to object storage.
- Add pgvector embeddings.
- Add OpenAI/Azure OpenAI provider.
- Add real auth and workspace permissions.
- Add structured logs and monitoring alerts.
