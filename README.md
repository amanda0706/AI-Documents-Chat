# LuminaClause

![Backend tests](https://github.com/amanda0706/AI-Documents-Chat/actions/workflows/backend-tests.yml/badge.svg)

> Local-first AI contract review workspace for summarizing agreements, asking grounded questions, comparing versions, and surfacing risky clauses before human review.

LuminaClause is built as a practical **AI Contract / Document Assistant** rather than a toy chatbot: it keeps the source text close, explains why a clause matters, and supports the review work around the document itself.

## Product snapshot

![LuminaClause interface concept](design/luminaclause-concept.png)

| Area | What it does |
| --- | --- |
| Understand | summaries, fragment search, grounded Q&A with citations |
| Review | risk detection, scoring, suggested safer wording |
| Compare | side-by-side contract comparison and impact notes |
| Collaborate | comments, sharing, review statuses, activity history |
| Operate | deadlines, review queue, dashboard, exportable reports |

## Product screenshots

### Dashboard

Portfolio metrics, risk triage, review queue, and deadline overview.

![LuminaClause dashboard](docs/screenshots/dashboard.png)

### Document workspace

Extracted clauses, AI summary, metadata, risk labels, and review controls.

![LuminaClause document workspace](docs/screenshots/document-workspace.png)

### Contract comparison

Side-by-side differences with an executive summary and impact notes.

![LuminaClause contract comparison](docs/screenshots/compare-contracts.png)

## Why it is useful

Contract review is often slow, repetitive, and opaque for non-lawyers. LuminaClause shortens the first-pass review loop by helping users:

1. find the important clauses,
2. understand the commercial impact,
3. keep every answer traceable to the original document,
4. move the contract through a lightweight human review workflow.

## Feature highlights

### 1. Explainable document chat

Questions return not only an answer, but also the supporting contract passages that justify it.

### 2. Contract risk review

The app highlights risky clauses, scores the document, and proposes safer wording that a reviewer can inspect before acting.

### 3. Review workflow

Each contract can move through `Draft`, `In review`, and `Approved`, with comments and activity history preserving the human review trail.

### 4. Portfolio-level triage

The dashboard shows high-risk contracts, items awaiting review, approved documents, and a review queue that puts the weakest agreements first.

### 5. Exportable output

Users can generate and download a markdown report that is ready to share or convert into a polished PDF later.

## Why the project is built this way

The product is intentionally developed **without cloud AI first**. That keeps the core workflow testable end-to-end while the local analysis layer acts as a clean substitute for the future provider layer.

Current local engine:

- PDF text extraction,
- sentence ranking,
- keyword-based retrieval,
- rules-based risk detection,
- deterministic suggestions,
- local JSON persistence.

Optional local OCR:

- native PDF text extraction runs first,
- scanned PDFs can fall back to OCR when the optional OCR dependencies are installed,
- OCR uses PyMuPDF with a locally installed Tesseract engine,
- enable the optional path with `pip install -r backend/requirements-ocr.txt`.

Provider architecture:

- a shared analysis provider contract,
- a local provider active today,
- a clean seam for future OpenAI / Azure OpenAI providers.

Configuration today:

```env
ANALYSIS_PROVIDER=local
```

The app already reads the provider choice from environment variables, so switching intelligence backends later does not require changing the product flow.

Future provider layer:

- OpenAI / Azure OpenAI for richer summaries and Q&A,
- embeddings for semantic retrieval,
- PostgreSQL + pgvector,
- object storage,
- hosted deployment.

## Product shape

### Core

- Document workspace
- AI summary
- risk analysis
- Q&A
- fragment search

### Pro-style features

- contract comparison
- scoring
- AI suggestions
- multi-language flag
- sharing
- dashboard
- review comments
- review status workflow
- review queue
- exportable reports

## Stack

- Frontend: Next.js + TypeScript + Tailwind
- Backend: Python + FastAPI
- Storage now: local filesystem + JSON
- Planned persistence: PostgreSQL + pgvector
- Planned cloud: AWS or Azure

## Architecture

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

The product is intentionally split so the user-facing workflow can stay stable while the intelligence layer evolves from local heuristics to hosted AI and vector search.

## Local run

### Fast path on Windows

```powershell
.\scripts\check-local.cmd
.\scripts\bootstrap.cmd
.\scripts\run-local.cmd
```

That flow:

- checks whether Python, Node.js, and npm are available,
- creates the backend virtual environment,
- installs backend and frontend dependencies,
- creates local environment files from examples,
- starts both services together.

If you prefer manual control, use the steps below.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Optional OCR support

For scanned PDFs, install the optional OCR dependencies and Tesseract locally:

```powershell
cd backend
pip install -r requirements-ocr.txt
```

You also need the Tesseract executable available on your machine. PyMuPDF invokes Tesseract for OCR pages, so the main app remains usable even when OCR is not installed.

### Frontend

```powershell
cd frontend
npm install
npx next dev -p 3004
```

Open:

- frontend: `http://localhost:3004`
- backend docs: `http://localhost:8000/docs`

## Local demo fallback

If package installation is blocked on a given machine, there is also a lightweight local demo mode that reuses the same analysis logic but runs on libraries already available in the environment:

```powershell
python local_demo\app.py
```

Then open:

- local demo: `http://127.0.0.1:5050`

## Quick demo path

1. Start the backend and frontend, or use the lightweight local demo mode.
2. Upload `samples/master-services-agreement.txt`.
3. Upload `samples/supplier-agreement.txt`.
4. Ask: `What are the payment terms?`
5. Add a reviewer comment and move the first contract into `In review`.
6. Open the comparison view and compare both documents.
7. Inspect the review queue, suggested edits, and supporting passages below the answer.
8. Generate and download a contract review report.

## What makes this portfolio-ready

- Real product framing around a concrete workflow, not just generic chat
- Full-stack delivery across Next.js and FastAPI
- Explainable AI-oriented architecture with citations and a swappable provider layer
- Workflow features beyond MVP: comments, status, deadlines, review queue, export
- Automated backend and API tests
- Fresh-clone bootstrap scripts for repeatable setup
- Clear migration path from local prototype to hosted AI and cloud persistence


## Validation

Current local checks:

- Backend test suite: `31 passed`
- Frontend production build: `next build` passes
- Manual end-to-end flow verified: upload -> analysis -> document view -> compare

## Fresh-clone checklist

After cloning the repository on a new machine:

1. Run `.\scripts\check-local.cmd`
2. Run `.\scripts\bootstrap.cmd`
3. Run `.\scripts\run-local.cmd`
4. Open `http://localhost:3004`
5. Upload the files from `samples/`
6. Confirm that backend tests pass with `python -m pytest backend/tests`

## Main API endpoints

- `GET /dashboard`
- `GET /documents`
- `POST /documents/upload`
- `GET /documents/{id}`
- `GET /documents/{id}/search`
- `POST /documents/{id}/ask`
- `POST /documents/{id}/share`
- `POST /documents/{id}/comments`
- `POST /documents/{id}/status`
- `GET /documents/{id}/report`
- `POST /compare`

## Demo materials

The `samples/` directory contains two small contract examples that are useful when demonstrating the comparison and risk-analysis flow. They can be uploaded directly as `.txt` files:

- `master-services-agreement.txt`
- `supplier-agreement.txt`

## Roadmap toward production

1. Replace local heuristic analysis with provider adapter
2. Add PostgreSQL + pgvector
3. Add real authentication and permissions
4. Store files in S3 / Blob Storage
5. Add audit log, comments, and workspace roles
6. Deploy frontend + backend
