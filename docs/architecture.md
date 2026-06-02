# LuminaClause architecture

```text
Next.js frontend
      |
      v
FastAPI backend
      |
      +--> local document store (JSON / filesystem)
      +--> AnalysisProvider interface
              |
              +--> LocalProvider       (default, no key required)
              +--> ClaudeProvider      (stub — set ANTHROPIC_API_KEY)
              +--> OpenAIProvider      (stub — set OPENAI_API_KEY)
```

## Current mode

- Documents are stored locally.
- Metadata is stored in JSON.
- Analysis runs through a provider interface (`AnalysisProvider`).
- The active provider is deterministic, local, and explainable.
- Provider selection is configuration-driven through `ANALYSIS_PROVIDER`.
- Core API payloads use validated enums and date-shaped metadata fields.

## Provider configuration

| `ANALYSIS_PROVIDER` | Key required | Status |
|---|---|---|
| `local` (default) | none | active |
| `claude` | `ANTHROPIC_API_KEY` | stub ready |
| `openai` | `OPENAI_API_KEY` | stub ready |

Selecting a cloud provider without the matching key raises a clear `ValueError` at startup. The optional `AI_MODEL` variable overrides the default model for the selected provider.

## Future mode

- PostgreSQL stores users, documents, chats, shares, and clause metadata.
- pgvector stores embeddings.
- Object storage keeps the original files.
- Cloud provider stubs (`ClaudeProvider`, `OpenAIProvider`) are wired to real SDK calls.

## Why this split matters

The frontend already speaks to stable backend endpoints, while the backend now speaks to a provider contract. That means the intelligence layer can improve dramatically later without forcing a product rewrite.

## Current local capabilities

- Landing page with product positioning and GitHub CTA.
- Drag-and-drop PDF/TXT upload with visible progress states.
- Document-grounded Q&A with local conversation history and cited fragments.
- Review workflow: comments, status, metadata, deadlines, and activity timeline.
- Archive workflow through `DELETE /documents/{id}` and the UI danger zone.
- API resilience in the frontend so failed backend calls return controlled empty states instead of a framework overlay.

## Container runtime

Docker Compose runs two services:

- `frontend`: Next.js production server on port `3000`.
- `backend`: FastAPI service on port `8000`, with `/app/data` persisted in the `backend-data` volume.

The frontend uses `NEXT_PUBLIC_API_URL=/api` in the browser and `INTERNAL_API_URL=http://backend:8000` for server-side rewrites inside the Docker network.


## Operational readiness

The backend exposes `/health` for uptime checks and `/metrics` for a compact local observability snapshot. Today the metrics are computed from the local JSON store; after deployment they can feed cloud logs, dashboards, or alerting without changing the product workflow.
