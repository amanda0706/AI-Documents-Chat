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

## Production migration notes

Current persistence is local JSON/filesystem. The API is intentionally shaped so these routes can later be backed by:

- real authentication and workspace permissions,
- PostgreSQL + pgvector,
- object storage for original files,
- OpenAI/Azure OpenAI provider adapters,
- hosted observability and audit logging.
