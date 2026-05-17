# ClausePilot architecture

```text
Next.js frontend
      |
      v
FastAPI backend
      |
      +--> local document store
      +--> analysis provider interface
              |
              +--> local provider now
              +--> hosted provider later
```

## Current mode

- Documents are stored locally.
- Metadata is stored in JSON.
- Analysis runs through a provider interface.
- The active provider is deterministic, local, and explainable.

## Future mode

- PostgreSQL stores users, documents, chats, shares, and clause metadata.
- pgvector stores embeddings.
- Object storage keeps the original files.
- A hosted provider can replace the local provider without changing the product workflow.

## Why this split matters

The frontend already speaks to stable backend endpoints, while the backend now speaks to a provider contract. That means the intelligence layer can improve dramatically later without forcing a product rewrite.
