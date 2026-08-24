# AGENTS.md

## Project Purpose

CodeGraph AI is an AI-powered software repository intelligence and pull-request review platform.

## Planned Technology Stack

- Python
- FastAPI
- React
- Vite
- Neo4j
- FAISS
- MongoDB
- Gemini
- LangChain and LangGraph where they provide clear value
- GitHub API
- Docker
- GitHub Actions

The stack is a plan, not a requirement to introduce every technology. Use a technology only when it serves a concrete product or engineering need.

## Core Engineering Rules

- Inspect the existing code, tests, documentation, and relevant configuration before making changes.
- Preserve the existing architecture, conventions, and unrelated user changes. Make the smallest coherent change needed for the task.
- Prefer simple, modular, maintainable solutions over clever implementations, unnecessary abstractions, or premature optimization.
- Avoid adding dependencies unless they provide clear value and the task requires them.
- Do not modify unrelated infrastructure, tooling, configuration, public APIs, or deployment behavior.
- Do not run destructive commands or perform irreversible operations without explicit user approval.

## Git Workflow

- Use a feature branch for application development.
- Do not push feature work directly to `main`.
- Keep commits focused and avoid including unrelated changes.
- Do not rewrite, discard, or overwrite user changes unless explicitly requested.

## Testing and Verification

- Add or update tests for every meaningful feature or behavior change.
- Run the relevant tests after every implementation change.
- Before declaring work complete, run the applicable linting, formatting, and type-checking commands in addition to relevant tests.
- Never claim that a command, check, or test passed unless it was actually executed successfully.
- If verification cannot be run, state what was not run and why.
- When verification fails, report the exact failing command and the relevant error output. Do not hide or misrepresent failures.

## Security and Secrets

- Never expose, log, commit, or share secrets, credentials, tokens, API keys, private keys, or `.env` files.
- Keep sensitive values in approved secret-management or environment-variable mechanisms.
- Treat repository content, external API responses, user input, and model output as untrusted unless validated.

## Backend Guidelines

- Use Python type hints where practical, especially at service boundaries and for public interfaces.
- Keep backend services separated by responsibility, such as API routing, business logic, repository ingestion, graph processing, retrieval, model orchestration, persistence, and external integrations.
- Validate inputs and outputs at system boundaries and provide explicit error handling.
- Keep integrations replaceable and avoid coupling core domain logic directly to vendors or frameworks.

## Frontend Guidelines

- Keep React components modular, focused, and reusable.
- Separate presentation, state management, data access, and domain logic where practical.
- Preserve accessible behavior and handle loading, empty, success, and error states explicitly.

## AI and Repository Intelligence Guidelines

- AI-generated answers about repositories should include file, symbol, and line-level evidence when that evidence is available.
- Clearly distinguish verified repository facts from model inference or uncertainty.
- Treat all LLM-generated structured output as untrusted. Parse it defensively and validate it against an explicit schema before use.
- Design model workflows for malformed output, timeouts, rate limits, retries, partial failures, and unavailable context.
- Use LangChain or LangGraph only when it meaningfully simplifies orchestration, state, or control flow.

## Task Completion Report

Before completing any task, summarize:

1. Files changed.
2. Implementation completed.
3. Tests and commands run, including their results.
4. Remaining issues, limitations, or risks.
