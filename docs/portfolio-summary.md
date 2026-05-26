# LuminaClause portfolio summary

## One-line pitch

LuminaClause is a local-first AI document review workspace for contract upload, grounded Q&A, risk analysis, comparison, review workflow, and production-ready API operations.

## CV version

**LuminaClause — AI Contract Review Assistant**  
Built a full-stack document assistant using Next.js, TypeScript, FastAPI, and Python. The app supports PDF/TXT upload, local document analysis, grounded Q&A with citations, semantic retrieval, contract comparison, risk scoring, review workflow, ownership mock, markdown reports, Docker runtime, API documentation, CI checks, and operational health/metrics endpoints.

## Recruiter-friendly summary

This project demonstrates how I design and ship an AI-style SaaS product end-to-end: user experience, backend APIs, local persistence, analysis abstraction, testing, documentation, and deployment readiness. The current MVP runs without cloud AI so the workflow is reliable and testable, while the architecture is prepared for OpenAI/Azure OpenAI, embeddings, PostgreSQL, pgvector, object storage, and cloud deployment.

## Engineering highlights

- Built a polished Next.js dashboard with upload, document workspace, Q&A, comparison, suggestions, metadata, review status, comments, and archive flows.
- Designed FastAPI endpoints for document lifecycle, chat, retrieval, reports, deadlines, metrics, and review collaboration.
- Added a provider layer so the local analysis engine can later be replaced with OpenAI/Azure OpenAI without rewriting the product flow.
- Implemented local RAG-ready retrieval with scored source fragments and citations.
- Added validation for uploads, including file type checks, empty file handling, file size limits, and safe filenames.
- Added backend tests, frontend build CI, Docker Compose runtime, Swagger/OpenAPI docs, API reference, architecture notes, and release checklist.

## Demo story

1. Open the landing page and explain the product: contract review assistant for faster first-pass review.
2. Log in with any email to enter the local workspace.
3. Upload a sample `.txt` or `.pdf` contract.
4. Show the dashboard: risk score, review queue, deadlines, ownership, and portfolio metrics.
5. Open the document workspace and show extracted fragments, AI summary, risks, metadata, and comments.
6. Ask a contract question and show that the answer includes citations/source passages.
7. Run semantic retrieval to show RAG-style context search.
8. Compare two documents and show the difference summary.
9. Generate a markdown report.
10. Mention Docker, tests, CI, API docs, `/health`, `/metrics`, and future cloud/AI migration path.

## Future roadmap

- Real authentication and workspaces.
- PostgreSQL + pgvector persistence.
- OpenAI/Azure OpenAI provider for summaries, chat, and embeddings.
- Cloud deployment: Vercel frontend + Render/Railway backend, then AWS/Azure migration.
- Object storage for original documents.
- Streaming AI answers and richer audit logs.
