# CodeGraph AI

CodeGraph AI is an AI-powered repository intelligence and pull-request review platform. This foundation provides a modular FastAPI backend, a minimal React/Vite dashboard, and local MongoDB and Neo4j services. Repository ingestion, parsing, retrieval, AI, and review behavior are intentionally not implemented yet.

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
  app/modules/        Future feature boundaries
frontend/             React/Vite dashboard and API service layer
docs/                 Architecture and delivery scope
compose.yaml          Local MongoDB and Neo4j services
```

The empty feature packages under `backend/app/modules` reserve clear boundaries for ingestion, analysis, graph access, retrieval, AI providers, GitHub integration, and pull-request reviews without implementing those features prematurely.

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
| `MONGO_ROOT_USERNAME`, `MONGO_ROOT_PASSWORD` | Local MongoDB initialization credentials |
| `NEO4J_HOST`, `NEO4J_BOLT_PORT` | Backend Neo4j readiness target |
| `NEO4J_BIND_HOST`, `NEO4J_HTTP_PORT` | Host interface and browser port for local Neo4j |
| `NEO4J_USERNAME`, `NEO4J_PASSWORD` | Local Neo4j credentials |

## Current scope

Implemented now:

- FastAPI application factory and versioned health/readiness API.
- Dependency readiness abstraction with MongoDB and Neo4j TCP checks.
- Minimal React dashboard with an API service layer.
- Database-only Docker Compose configuration with persistent volumes and health checks.
- Backend and frontend tests that do not need external services.

Explicitly deferred:

- Repository ingestion and source parsing.
- Neo4j graph writes and MongoDB persistence adapters.
- FAISS and embeddings.
- Gemini, LangChain, and LangGraph.
- GitHub pull-request analysis and reviews.
