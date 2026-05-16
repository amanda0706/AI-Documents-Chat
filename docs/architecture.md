# ClausePilot architecture

```text
Next.js frontend
      |
      v
FastAPI backend
      |
      +--> local document store
      +--> local analyzer
      +--> future provider adapter
```

## Current mode

- Documents are stored locally.
- Metadata is stored in JSON.
- Analysis is deterministic and explainable.

## Future mode

- PostgreSQL stores users, documents, chats, shares, and clause metadata.
- pgvector stores embeddings.
- Object storage keeps the original files.
- Provider adapter swaps the local analyzer for hosted LLMs.

## Why this split matters

The frontend already speaks to stable backend endpoints. That means the intelligence layer can improve dramatically later without forcing a product rewrite.
