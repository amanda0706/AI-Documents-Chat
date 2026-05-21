# LuminaClause architecture

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
- Provider selection is configuration-driven through `ANALYSIS_PROVIDER`.
- Core API payloads use validated enums and date-shaped metadata fields.

## Future mode

- PostgreSQL stores users, documents, chats, shares, and clause metadata.
- pgvector stores embeddings.
- Object storage keeps the original files.
- A hosted provider can replace the local provider without changing the product workflow.

## Why this split matters

The frontend already speaks to stable backend endpoints, while the backend now speaks to a provider contract. That means the intelligence layer can improve dramatically later without forcing a product rewrite.

## Current local capabilities

- Landing page with product positioning and GitHub CTA.
- Drag-and-drop PDF/TXT upload with visible progress states.
- Document-grounded Q&A with local conversation history and cited fragments.
- Review workflow: comments, status, metadata, deadlines, and activity timeline.
- Archive workflow through `DELETE /documents/{id}` and the UI danger zone.
- API resilience in the frontend so failed backend calls return controlled empty states instead of a framework overlay.
