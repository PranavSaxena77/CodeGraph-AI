# CodeGraph AI

CodeGraph AI is an AI-powered repository intelligence and pull-request review platform. The current foundation provides a modular FastAPI backend, a minimal React/Vite dashboard, public GitHub repository ingestion, deterministic Python analysis, a Neo4j code graph, and snapshot-scoped semantic vector retrieval.

## Prerequisites

- Python 3.12
- Node.js 20 and npm
- Docker with Docker Compose

## Project structure

```text
backend/              FastAPI modular monolith and tests
  app/api/            Versioned HTTP routes
  app/core/           Runtime configuration
  app/domain/         Provider-independent models
  app/services/       Application services and interfaces
  app/modules/        Ingestion, analysis, graph, and future feature boundaries
frontend/             React/Vite dashboard and API service layer
docs/                 Architecture and delivery scope
compose.yaml          Local MongoDB and Neo4j services
```

Feature packages under `backend/app/modules` separate ingestion, analysis, graph persistence, retrieval, AI, GitHub, and pull-request review responsibilities.

## Local setup

Copy the safe configuration template and replace every placeholder credential with a local value:

```bash
cp .env.example .env
```

The `.env` file is ignored by Git. Never commit it or place production credentials in local development files.

### Backend

Create an isolated Python 3.12 environment and install only the backend and development dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
```

Start the API from the repository root:

```bash
uvicorn app.main:app --app-dir backend --reload
```

The API is available at `http://localhost:8000`:

- `GET /api/v1/health` reports process health without external connections.
- `GET /api/v1/ready` returns `200` when MongoDB and Neo4j are reachable, otherwise `503`.
- `POST /api/v1/repositories` registers and indexes a public GitHub repository snapshot.
- `GET /api/v1/repositories/{repository_id}` returns stored repository metadata.
- `GET /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}` returns snapshot status and discovery metadata.
- `POST /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/analysis` returns deterministic Python structural analysis for an ingested snapshot.
- `POST /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/graph` analyzes and idempotently persists a snapshot code graph.
- `GET /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/graph` returns graph persistence status and counts.
- `POST /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-index` builds or reuses a snapshot-scoped FAISS index.
- `GET /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-index` returns vector-index status.
- `POST /api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-search` searches an indexed snapshot with a validated `query` and `top_k`.
- Interactive API documentation is at `/docs`.

### Frontend

Install dependencies and start Vite:

```bash
cd frontend
npm install
npm run dev
```

The dashboard is available at `http://localhost:5173`. It reads `VITE_API_BASE_URL` from the root `.env` file and defaults to `http://localhost:8000/api/v1`.

### MongoDB and Neo4j

After configuring `.env`, start only the local data services:

```bash
docker compose up -d mongodb neo4j
docker compose ps
```

MongoDB listens on the configured `MONGODB_PORT`. Neo4j Browser and Bolt listen on `NEO4J_HTTP_PORT` and `NEO4J_BOLT_PORT`. Data persists in the `mongodb_data` and `neo4j_data` named volumes.

Stop services without deleting their data:

```bash
docker compose down
```

Deleting named volumes is intentionally not part of the normal workflow because it destroys local data.

## Verification

With the Python environment active, run backend checks from `backend`:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pytest
```

Run frontend checks from `frontend`:

```bash
npm test
npm run build
```

Validate the Compose model from the repository root:

```bash
docker compose config --quiet
```

Basic tests inject fake dependency checks and do not require GitHub, Gemini, MongoDB, or Neo4j.

## Configuration

All runtime configuration comes from environment variables. Backend settings also load the ignored root `.env` file for local development. Docker Compose requires database credentials to be set and does not contain hardcoded passwords.

| Variable | Purpose |
|---|---|
| `APP_NAME`, `APP_VERSION` | API metadata and health response |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `VITE_API_BASE_URL` | Frontend API base URL |
| `MONGODB_HOST`, `MONGODB_PORT` | Backend MongoDB readiness target |
| `MONGODB_BIND_HOST` | Host interface used for the local MongoDB port |
| `MONGODB_DATABASE` | MongoDB metadata database |
| `MONGO_ROOT_USERNAME`, `MONGO_ROOT_PASSWORD` | Local MongoDB initialization credentials |
| `NEO4J_HOST`, `NEO4J_BOLT_PORT` | Backend Neo4j readiness target |
| `NEO4J_BIND_HOST`, `NEO4J_HTTP_PORT` | Host interface and browser port for local Neo4j |
| `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | Neo4j credentials and database |
| `GITHUB_API_BASE_URL`, `GITHUB_TIMEOUT_SECONDS` | Public GitHub REST API configuration |
| `MAX_ARCHIVE_*` | Repository archive safety limits |
| `EMBEDDING_PROVIDER`, `EMBEDDING_FAKE_DIMENSION` | Embedding adapter selection and local deterministic dimension |
| `GEMINI_API_KEY`, `GEMINI_EMBEDDING_*`, `GEMINI_REASONING_MODEL` | Optional Gemini embedding and grounded-reasoning configuration |
| `GEMINI_MAX_OUTPUT_TOKENS` | Maximum structured Q&A response size |
| `VECTOR_INDEX_ROOT`, `MAX_CHUNK_CHARS` | Snapshot index storage and deterministic chunk-size limit |
| `HYBRID_*`, `QA_*` | Hybrid retrieval and Q&A evidence budgets |

## Current scope

Implemented now:

- FastAPI application factory and versioned health/readiness API.
- Dependency readiness abstraction with MongoDB and Neo4j TCP checks.
- Public GitHub repository registration, immutable ref resolution, bounded archive download, safe extraction, Python-file discovery, and MongoDB metadata persistence.
- Deterministic Python AST analysis for files, classes, functions, methods, imports, inheritance, and conservative call references.
- Idempotent Neo4j snapshot graphs with scoped symbol, containment, call, import, dependency, and neighbor queries.
- Deterministic symbol-aware chunks, replaceable embedding providers, persistent exact FAISS indexes, and evidence-preserving semantic search.
- Snapshot-safe hybrid graph/vector retrieval with deterministic fusion and context budgets.
- Evidence-grounded repository Q&A with replaceable reasoning providers, validated citations, and optional Gemini generation.
- Minimal React dashboard with an API service layer.
- Database-only Docker Compose configuration with persistent volumes and health checks.
- Backend and frontend tests that do not need external services.

Explicitly deferred:

- LangChain and LangGraph orchestration.
- GitHub pull-request analysis and reviews.
