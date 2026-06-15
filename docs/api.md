# LuminaClause API reference

LuminaClause exposes a FastAPI backend for local contract upload, analysis, review workflow, and comparison.

Local URLs:

- API: `http://localhost:8000`
- Swagger/OpenAPI UI: `http://localhost:8000/docs`
- Frontend proxy in local Next.js/Docker: `/api/*`

## Health and dashboard

### `GET /health`

Returns service status.

```json
{ "status": "ok" }
```

### `GET /dashboard`

Returns portfolio-level review metrics.

```json
{
  "total_documents": 2,
  "high_risk_documents": 1,
  "average_score": 62,
  "shared_documents": 1,
  "pending_review_documents": 1,
  "approved_documents": 1,
  "expiring_soon_documents": 1,
  "renewal_due_documents": 1
}
```

### `GET /deadlines`

Returns expiry and renewal reminders derived from document metadata.

### `GET /metrics`

Returns an operational snapshot for local monitoring and future production observability.

```json
{
  "service": "luminaclause-api",
  "total_documents": 2,
  "total_fragments": 6,
  "total_risks": 3,
  "high_risk_documents": 1,
  "average_score": 62,
  "shared_documents": 1,
  "comments_count": 4,
  "activity_events": 9,
  "latest_upload_filename": "supplier-agreement.txt"
}
```

### `GET /provider`

Returns the active AI analysis provider.  Never exposes API keys or secrets.

```json
{ "provider": "local", "model": "local", "cloud_enabled": false }
```

| `provider` | meaning |
|---|---|
| `local` | on-device heuristics, no key required |
| `claude` | Anthropic Claude via `ANTHROPIC_API_KEY` |
| `openai` | OpenAI ChatGPT via `OPENAI_API_KEY` |

### `GET /runtime`

Returns the active storage backend and its readiness.  Never exposes `DATABASE_URL`, passwords, or any credentials.

```json
{ "storage_backend": "json", "storage_ready": true, "database_connected": null }
```

| `storage_backend` | `database_connected` | meaning |
|---|---|---|
| `json` | `null` | local JSON file, always ready |
| `postgres` | `true` | PostgreSQL reachable |
| `postgres` | `false` | PostgreSQL configured but unreachable |

The endpoint performs a lightweight `SELECT 1` ping only when `STORAGE_BACKEND=postgres`.
No check runs for the `json` backend, so there is no overhead on the default path.

## Documents

### `GET /documents`

Lists all stored documents visible to the local backend.

### `GET /documents/{id}`

Returns one document with metadata, fragments, summary, risks, suggestions, activity, comments, and review status.

### `DELETE /documents/{id}`

Archives/removes a document from the local store.

```json
{
  "status": "deleted",
  "document_id": "..."
}
```

## Uploads

### `POST /documents/upload`

Multipart form upload for a single PDF/TXT document.

Fields:

- `file`: PDF or TXT file
- `owner`: optional email used by the local auth/ownership mock

PowerShell example:

```powershell
curl.exe -X POST "http://localhost:8000/documents/upload" `
  -F "owner=anna@example.com" `
  -F "file=@samples/master-services-agreement.txt"
```

### `POST /documents/bulk-upload`

Multipart form upload for multiple PDF/TXT documents.

Fields:

- `files`: repeated file field
- `owner`: optional email

### Upload guardrails

The local API applies production-minded validation before analysis starts:

- `.pdf` and `.txt` only
- empty files rejected with `400`
- files above 5 MB rejected with `413`
- filenames sanitized before temporary storage
- unreadable documents rejected with a controlled `400`

## Versions

### `POST /documents/{id}/versions`

Uploads a new version into the selected document's version group.

### `GET /documents/{id}/versions`

Lists all versions in the selected document's version group.

## Search and document chat

### `GET /documents/{id}/search?query=payment`

Returns matching fragments with similarity scores.

### `POST /documents/{id}/ask`

Asks a document-grounded question.

Request:

```json
{
  "question": "What are the payment terms?"
}
```

Response:

```json
{
  "answer": "...",
  "citations": [
    {
      "id": "...",
      "page": 1,
      "text": "Payment terms are net 60 days..."
    }
  ]
}
```

The frontend stores a local conversation history and renders answer/report markdown for reviewer readability.

## Review workflow

### `POST /documents/{id}/share`

```json
{ "email": "reviewer@example.com" }
```

### `POST /documents/{id}/comments`

```json
{
  "author": "anna@example.com",
  "body": "Please check the liability cap."
}
```

### `POST /documents/{id}/status`

Allowed statuses:

- `draft`
- `in_review`
- `approved`

```json
{ "status": "in_review" }
```

### `POST /documents/{id}/metadata`

Updates ownership and contract lifecycle metadata.

```json
{
  "owner": "anna@example.com",
  "counterparty": "Northwind Labs",
  "contract_type": "MSA",
  "effective_date": "2026-01-01",
  "expiry_date": "2026-12-31",
  "renewal_date": "2026-11-30"
}
```

## Reports and comparison

### `GET /documents/{id}/report`

Returns an exportable markdown review report.

### `POST /compare`

Compares two documents.

Request:

```json
{
  "left_id": "...",
  "right_id": "..."
}
```

Response includes an executive summary and categorized differences.

## Embeddings and vector retrieval

LuminaClause includes a RAG-ready vector retrieval layer.  Document fragments
are mapped to dense float vectors and stored in ``data/embeddings.json``.
Queries are embedded with the same function and the top-*k* fragments are
returned by cosine similarity.

**Current provider:** local deterministic hash-projection (128 dims, no API
key required).  Swap the embedding function in ``embeddings.py`` for a cloud
API (OpenAI ``text-embedding-3-small``, Cohere, etc.) or a local model
(``sentence-transformers``) without changing these endpoints.  See
``embeddings.py`` for the pgvector migration notes.

### `POST /embeddings/reindex`

Compute and store vector embeddings for document fragments.

Request body:

```json
{ "doc_id": "<id>" }
```

Omit `doc_id` (or pass `null`) to reindex every document in the store.
The operation is idempotent — existing records for the same fragment are
overwritten.

Response:

```json
{
  "indexed_documents": 1,
  "total_fragments": 14,
  "provider": "local",
  "dim": 128
}
```

### `GET /documents/{id}/embeddings`

Return embedding metadata for every indexed fragment of the document, sorted
by page number.

Query parameters:

| Parameter | Default | Description |
|---|---|---|
| `include_vectors` | `false` | Include raw float arrays in the response |

Vectors are omitted by default to keep payloads small.  Add
`?include_vectors=true` when you need the raw floats (e.g. for t-SNE /
UMAP visualisation on the client).

Returns `404` when no embeddings exist — run `POST /embeddings/reindex` first.

Response (without vectors):

```json
[
  {
    "document_id": "...",
    "fragment_id": "...-0",
    "page": 1,
    "text": "Payment terms are net sixty days...",
    "provider": "local",
    "dim": 128
  }
]
```

### `GET /documents/{id}/vector-search`

Retrieve the top-*k* fragments most similar to a query by cosine similarity.

Query parameters:

| Parameter | Default | Description |
|---|---|---|
| `query` | required | Natural-language search query |
| `top_k` | `3` | Number of results (clamped to 1–8) |

Returns `404` when no embeddings exist — run `POST /embeddings/reindex` first.
Returns `400` when `query` is empty.

This is the **RAG retrieval step**: concatenate the returned fragment texts as
grounding context for a language model answer.

Compared with `GET /documents/{id}/retrieval` (keyword overlap score), this
endpoint uses dense vector similarity and scales naturally to semantic
embeddings once the local function is replaced.

Response:

```json
{
  "query": "payment invoice",
  "top_k": 3,
  "provider": "local",
  "dim": 128,
  "results": [
    {
      "rank": 1,
      "fragment_id": "...-0",
      "page": 1,
      "text": "Payment terms are net sixty days from invoice date.",
      "score": 0.8213
    }
  ]
}
```

## AI provider configuration

All analysis routes (`/upload`, `/ask`, `/compare`, `/documents/{id}/versions`) run through the `AnalysisProvider` interface. The active provider is selected by the `ANALYSIS_PROVIDER` environment variable.

| Value | Key required | Notes |
|---|---|---|
| `local` (default) | none | deterministic, always works |
| `claude` | `ANTHROPIC_API_KEY` | stub ready; set key to activate |
| `openai` | `OPENAI_API_KEY` | stub ready; set key to activate |

Optional: set `AI_MODEL` to override the default model for the selected cloud provider.

If a cloud provider is selected without its key the backend raises a clear error at startup; no partial or silent fallback occurs.

## Production migration notes

Current persistence is local JSON/filesystem. The API is intentionally shaped so these routes can later be backed by:

- real authentication and workspace permissions,
- PostgreSQL + pgvector,
- object storage for original files,
- Claude / OpenAI provider adapters (stub seam already in place),
- hosted observability and audit logging.
