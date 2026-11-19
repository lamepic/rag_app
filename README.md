# rag

A production-grade retrieval-augmented generation (RAG) backend for research papers: upload PDFs, then ask questions and get streamed answers that cite paper, section and page.

Built with FastAPI, Supabase (Postgres + pgvector, Storage, Auth), Redis, Celery and OpenAI.

## Status

Milestone M0 (project setup). See the roadmap for the full plan.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [Docker](https://docs.docker.com/get-docker/)
- [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)

## Getting started

```bash
cp .env.example .env
make install
make dev        # starts Supabase + Redis, runs migrations, serves the API on :8000
```

Then open http://127.0.0.1:8000/docs.

## Commands

Run `make` to list them all. The main ones:

| Command | Does |
| --- | --- |
| `make dev` | Start services, migrate, run the API with auto-reload |
| `make check` | Lint, format check, type check and tests (what CI runs) |
| `make fmt` | Auto-fix lint issues and reformat |
| `make down` | Stop services (data is kept) |
