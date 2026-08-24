# CodeGraph AI delivery scope

## 1. Delivery rule

CodeGraph AI will ship in three focused milestones:

| Release | Target | Outcome |
|---|---|---|
| v0.1 | Around September 15 | Resume-ready repository ingestion, structural indexing, hybrid retrieval, and evidence-backed Q&A |
| v0.5 | After v0.1 | Pull-request intelligence and basic graph exploration |
| v1.0 | By September 30 | Evaluated, tested, observable, deployed, and polished release |

The release numbers describe delivery sequence, not separate architectures. All releases use the modular-monolith design in `ARCHITECTURE.md`. This document governs milestone placement where the architecture document still uses the earlier P0/P1/P2 terminology.

Work must complete and verify each milestone before starting optional work from a later milestone. Safety, deterministic parsing, LLM-output validation, and evidence integrity are release requirements, not production-hardening tasks that may be deferred.

## 2. v0.1 — resume-ready core release

**Target:** Around September 15.

**Goal:** Demonstrate one complete, credible Python-first flow: provide a public GitHub repository, index it into graph and vector representations, ask repository questions, and receive grounded answers with verifiable source evidence.

### Public repository ingestion

- Accept a canonical public GitHub owner/repository and optional ref.
- Use read-only GitHub access to resolve the repository and pin analysis to an immutable commit SHA.
- Download the source archive without running Git hooks, builds, package managers, or repository code.
- Extract archives safely, rejecting absolute paths, path traversal, unsafe links, and files outside the job workspace.
- Apply practical limits for repository size, file count, individual file size, binary files, and unsupported files.
- Process accepted files in deterministic path order.

### Python structural analysis

- Parse Python source using the standard-library AST.
- Extract files, classes, functions, methods, imports, inheritance, and conservatively resolvable calls.
- Record deterministic IDs, qualified symbol names, and accurate one-based source spans.
- Preserve unresolved imports and calls as unresolved rather than guessing targets.
- Report unsupported or unparsable files without preventing useful files from being indexed.
- Never import, execute, compile, test, or install dependencies from the analyzed repository.

### Neo4j code knowledge graph

- Store repository, snapshot, file, class, function, and method nodes.
- Store containment, declaration, resolved import, inheritance, and conservatively resolved call relationships.
- Scope every node and query to the correct repository and immutable snapshot.
- Use stable keys and idempotent writes so retries do not create duplicate graph entities.

### Semantic chunks, embeddings, and FAISS

- Create semantic chunks around files, classes, functions, and methods.
- Retain file path, symbol identity, and exact line range on every chunk.
- Split oversized symbols using bounded, deterministic rules.
- Generate embeddings through a replaceable provider interface.
- Build one exact-search FAISS index and evidence mapping per snapshot.
- Validate the FAISS manifest, model, dimensions, and chunk mapping before retrieval.

### Independent and hybrid retrieval

- Expose graph retrieval and vector retrieval as independently testable services.
- Support graph-only and vector-only retrieval for tests and diagnostics.
- Combine candidates with deterministic rank fusion and bounded boosts for exact path or symbol matches.
- Deduplicate overlapping evidence and apply a strict context budget.
- Filter every retrieval operation by repository and snapshot.

### Gemini repository Q&A

- Send only selected, bounded repository evidence to Gemini.
- Keep embedding and reasoning providers replaceable behind interfaces.
- Require a structured response and validate it before it enters application state.
- Treat repository content as untrusted data, not instructions to the model or application.
- Reject fabricated, unknown, or malformed citation IDs.
- Construct returned citations from server-owned evidence, not model-provided paths or line numbers.
- Return evidence-backed answers containing commit-pinned file paths, symbols, and line ranges.
- Return an explicit insufficient-evidence result instead of inventing an answer.

### FastAPI backend and MongoDB metadata

- Provide a modular FastAPI backend for repository registration, indexing status, and repository questions.
- Use Pydantic request, response, domain-boundary, and LLM-output validation where appropriate.
- Store repository, snapshot, indexing-job, vector-manifest, and question metadata in MongoDB.
- Keep GitHub, Neo4j, MongoDB, FAISS, embeddings, and Gemini behind replaceable adapters.
- Provide simple, safe error responses for invalid input, missing resources, size limits, and unavailable dependencies.
- Use an in-process indexing runner for v0.1 and document its single-process and restart limitations.

### Minimal React and Vite frontend

- Provide a minimal JavaScript React/Vite interface.
- Support repository registration, indexing-status display, question submission, and answer display.
- Render evidence as file path, symbol, and line range.
- Handle loading, empty, success, and error states.
- Avoid a design system, global state framework, or advanced visualization in v0.1.

### Local development workflow

- Use Docker Compose to run Neo4j and MongoDB locally.
- Run the backend and frontend through clear, minimal development commands.
- Keep service credentials and API keys in uncommitted runtime environment configuration.
- Never expose, log, or commit credentials, tokens, secrets, API keys, or `.env` files.
- Provide a clean-clone, README-ready workflow covering environment setup, service startup, backend startup, frontend startup, tests, and shutdown.
- Do not require developers to install Neo4j or MongoDB directly on their machines.

### Core tests

- Add unit tests for safe archive extraction, deterministic IDs, Python AST extraction, source spans, chunking, FAISS mappings, rank fusion, and LLM-output/citation validation.
- Add FastAPI tests for the repository, indexing-status, question, validation-failure, and dependency-failure paths.
- Inject fakes so unit and API tests do not require live GitHub, Gemini, Neo4j, or MongoDB connections.
- Use small repository fixtures with known file, symbol, relationship, and line expectations.
- Run the applicable tests, linting, formatting, type checks, and frontend build checks before v0.1 is declared complete.

### Non-negotiable v0.1 safeguards

- Never execute analyzed repository code.
- Prevent unsafe archive extraction and path traversal.
- Never expose or commit secrets, credentials, tokens, API keys, or `.env` files.
- Validate all LLM-generated structured output.
- Reject fabricated evidence and citations.
- Keep GitHub access read-only.
- Preserve deterministic parsing, stable source spans, and evidence grounding.

### v0.1 acceptance criteria

v0.1 is complete only when:

1. A bounded public Python repository can be registered and indexed at a pinned commit.
2. Files and supported Python symbols/relationships are queryable in Neo4j.
3. Semantic chunks and their evidence mappings are searchable through FAISS.
4. Graph-only and vector-only retrieval work independently, and hybrid retrieval combines them deterministically.
5. A repository question returns a Gemini-generated answer with valid file, symbol, and line evidence.
6. Invalid model output and fabricated citation IDs are rejected safely.
7. The minimal frontend completes the register, index, ask, and inspect-evidence flow.
8. Neo4j and MongoDB start through Docker Compose, and the documented developer workflow works from a clean clone.
9. Core unit and API tests and applicable quality checks pass.

### Explicitly deferred from v0.1

The following must not delay the resume-ready core release:

- Pull-request ingestion or review.
- Graph visualization.
- GitHub Actions or automated deployment.
- Production hosting, high availability, backups, or multi-process workers.
- A durable queue, webhook processing, authentication, authorization, or private repositories.
- Advanced observability beyond useful sanitized development logs.
- Retrieval evaluation dashboards or large evaluation datasets.
- Incremental indexing.
- JavaScript or TypeScript parsing.
- Automatic GitHub comments or any write access to GitHub.
- Advanced UI polish, a design system, or complex client-state management.

## 3. v0.5 — developer intelligence release

**Target:** Begin after v0.1 is complete and verified.

**Goal:** Extend the indexed repository into an evidence-backed pull-request intelligence workflow.

### Pull-request intelligence

- Ingest GitHub pull-request metadata, immutable base/head SHAs, changed files, and available patches through the read-only GitHub REST API.
- Map Python diff hunks to changed files, classes, functions, and methods.
- Identify added, modified, and deleted symbols where deterministically derivable.
- Traverse the code graph from changed files and symbols to bounded callers, importers, dependencies, and related components.
- Combine diff evidence, graph impact candidates, and vector-retrieved context.
- Generate a structured Gemini review containing a summary, potentially affected components, evidence-backed findings, and suggested tests/checks.
- Validate every review finding and citation against server-provided diff or repository evidence.
- Flag unsupported files and truncated patches rather than overstating review coverage.
- Store and display review status and results in the application.
- Keep review behavior read-only; do not post comments, approvals, or changes to GitHub.

### Basic interactive graph visualization

- Render a bounded repository or symbol-centered subgraph, not the entire graph at once.
- Allow basic pan, zoom, node selection, and relationship inspection.
- Link graph nodes to file, symbol, and line evidence where available.
- Reuse existing graph API/query boundaries rather than adding a separate graph service.

### v0.5 acceptance criteria

1. A PR against an indexed Python repository can be ingested at immutable base/head SHAs.
2. Changed Python lines map to source symbols when spans permit it.
3. Affected-component candidates are derived from bounded graph traversal and labeled as candidates rather than facts.
4. The AI review report contains only validated evidence references.
5. Unsupported or incomplete analysis is visible to the user.
6. A user can explore a bounded graph view and navigate from a node to source evidence.
7. Unit/API tests cover diff mapping, impact traversal, report validation, and graph-view data responses.

## 4. v1.0 — polished release

**Target:** By September 30.

**Goal:** Turn the demonstrated core and developer-intelligence flows into an evaluated, deployed, and polished release.

### Required v1.0 work

- Build a repeatable evaluation framework comparing vector-only, graph-only, and hybrid retrieval on the same question/evidence set.
- Report retrieval and answer-quality measures with documented dataset assumptions and limitations.
- Add GitHub Actions for backend linting, formatting, type checks, tests, frontend checks/build, and container-build validation.
- Add a simple deployment path for the frontend, backend, MongoDB, Neo4j, and persistent FAISS indexes.
- Increase test coverage around adapters, failure paths, snapshot consistency, retrieval regressions, and critical frontend states.
- Improve error classification, user-facing failures, structured logging, request/job correlation, and dependency diagnostics.
- Improve ingestion and embedding batching, context-budget use, common-query latency, and bounded-resource behavior based on measurements.
- Polish repository setup, indexing progress, answer evidence, PR review, graph exploration, responsiveness, and accessibility.
- Document deployment, secrets, operational limitations, and recovery expectations.

### Feasibility-gated v1.0 work

These are valuable but are not release blockers if they threaten the September 30 target:

- Incremental indexing that reuses unchanged analysis and embeddings by content hash.
- JavaScript and TypeScript parsing through Tree-sitter using the shared internal representation.
- Conservative JavaScript/TypeScript import, export, class, function, method, and call extraction.

Feasibility-gated work may begin only after the required v1.0 evaluation, CI/CD, deployment, testing, observability, performance, and UX work is on track.

### v1.0 acceptance criteria

1. The same evaluation dataset can compare vector-only, graph-only, and hybrid retrieval reproducibly.
2. CI blocks changes that fail the agreed backend and frontend quality checks.
3. The application is deployed to a documented target environment with secrets kept outside source control.
4. Core ingestion, Q&A, PR review, and graph exploration flows have tested failure behavior and usable diagnostics.
5. Performance and repository-size limits are documented from actual measurements.
6. The primary UI flows are coherent, responsive, accessible at a basic level, and evidence-focused.
7. Incremental indexing and JavaScript/TypeScript support are included only if completed and verified without weakening required release work.

## 5. Delivery sequence and scope controls

1. Complete deterministic ingestion and Python analysis before adding Gemini reasoning.
2. Complete independent graph and vector retrieval before implementing hybrid fusion.
3. Complete evidence validation before presenting model answers in the UI.
4. Complete the v0.1 repository Q&A vertical slice before starting PR ingestion.
5. Complete deterministic PR change/impact facts before asking Gemini for a review.
6. Establish the evaluation baseline before tuning hybrid retrieval for v1.0.
7. Prefer reducing UI polish, repository-size limits, or optional analysis depth over weakening safeguards, evidence grounding, or core tests.

The project must remain a modular monolith through v1.0 unless measured constraints prove that a component must be separated. LangChain is optional. LangGraph should be introduced only if orchestration develops real branching, recovery, or human-approval complexity.

## 6. Out of scope through v1.0

- Broad multi-language support beyond Python and feasibility-gated JavaScript/TypeScript.
- Executing, compiling, testing, or installing dependencies from analyzed repositories.
- Fully sound static analysis for dynamic language behavior.
- Autonomous code changes, commits, merges, or pull-request approvals.
- Automatic GitHub comments or other write operations.
- Arbitrary Git hosts or arbitrary clone/archive URLs.
- Self-hosted model training, fine-tuning, or a custom embedding model.
- Kubernetes, a service mesh, or premature microservice decomposition.
- Multi-region, high-availability, or enterprise-scale deployment.
- Enterprise multi-tenancy, billing, SSO, RBAC, or compliance certification.
- Real-time collaboration, IDE extensions, or long-term source-code archival.

## 7. Architectural decisions and reasoning

| Decision | Delivery choice | Reasoning |
|---|---|---|
| Core release boundary | v0.1 ends at evidence-backed repository Q&A | This is the smallest resume-ready vertical slice that proves ingestion, parsing, graph, vector, retrieval, AI, API, and UI capabilities together |
| PR intelligence | v0.5 | PR ingestion, diff mapping, impact analysis, and review generation form a coherent second vertical slice and would put v0.1 at risk |
| Production hardening | v1.0 | CI/CD, deployment, evaluation, broader observability, and performance polish matter for a polished release but do not prove the core concept |
| Language sequence | Python first; JavaScript/TypeScript feasibility-gated for v1.0 | One reliable parser and evidence model are more valuable than shallow multi-language support |
| Repository access | Public and read-only | Avoids early authentication/authorization scope and prevents external write side effects |
| Processing model | One in-process worker initially | Avoids queue infrastructure while retaining an upgrade path through the job abstraction |
| Retrieval | Independent exact FAISS and bounded Neo4j retrieval with deterministic fusion | Keeps the core explainable, testable, and measurable |
| Model integration | Replaceable provider interfaces with validated structured output | Limits Gemini coupling and prevents untrusted model data from becoming application truth |
| Evidence | Server-owned citation IDs and source spans | Allows fabricated citations to be rejected and answers to remain auditable |
| Local services | Docker Compose for Neo4j and MongoDB | Provides reproducible infrastructure without local database installations |
| Frameworks | Plain services first; LangChain/LangGraph only when justified | Prevents orchestration frameworks from delaying the core vertical slice |

## 8. Known risks and constraints

- The v0.1 schedule is achievable only if PR analysis, graph visualization, deployment, CI/CD, incremental indexing, and JavaScript/TypeScript parsing remain deferred.
- Python import and call resolution will be conservative and incomplete.
- An in-process indexing runner limits concurrency and restart recovery.
- Maintaining one snapshot identity across MongoDB, Neo4j, and FAISS requires deterministic IDs and verified manifests.
- Exact FAISS search and local index files require bounded repository sizes.
- GitHub archives, rate limits, and external-provider availability can interrupt ingestion or Q&A.
- Model output validation can enforce structure and citation membership but cannot guarantee that every sentence is correct; evaluation remains required for v1.0.
- v0.1 without authentication is a local/single-user release and must not be exposed publicly.
- Docker images, temporary archives, and indexes require explicit storage limits and cleanup.
