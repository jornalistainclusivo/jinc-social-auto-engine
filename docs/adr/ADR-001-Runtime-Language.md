# ADR-001: Runtime Language & Core Application Stack

## Status

**Accepted**

## Context

The `jinc-social-engine` (JincSAE) requires a backend runtime capable of:

- Orchestrating external inputs (Webhooks, Social API calls).
- Strictly validating untrusted input at the system boundaries (LLM outputs, OAuth payloads, Social platform responses).
- Maintaining explicit domain state through a strict modular/hexagonal architecture.
- Executing human-in-the-loop and asynchronous background workflows for publishing.
- Integrating natively and rapidly with AI/LLM providers (OpenAI, Anthropic).

An initial analysis proposed TypeScript / Node.js, citing asynchronous I/O and structural typing. However, a formal Red Team adversarial review and subsequent Reconciliation Brief exposed methodological flaws in that recommendation (e.g., assuming MVP I/O volume necessitated Node.js, and ignoring the lack of native runtime safety in TypeScript).

## Decision

**Python is selected as the Runtime Language & Core Application Stack for JincSAE.**

## Rationale

The decision to adopt Python is based primarily on the following factors:

1. **AI-Assisted Orchestration Ecosystem:** Official AI SDKs (OpenAI, Anthropic) and advanced orchestration frameworks historically release beta features (like Structured Outputs and Prompt Caching) in Python first.
2. **Strong Runtime Validation Requirements:** Python, via Pydantic (Rust-core), provides exceptionally fast, deeply integrated, and ergonomic runtime validation for untrusted LLM and API payloads—an essential requirement for the AI Zero-Trust Boundary defined in the Engineering Constitution.
3. **Mature Async API Ecosystem:** Modern Python (via `asyncio`, FastAPI, and async drivers) is fully capable of handling the expected webhook and API ingestion volume for a newsroom MVP without creating a bottleneck.
4. **Tooling Alignment:** The existing `jinc-social-engine` repository relies heavily on Python for its operational and validation scripts (e.g., `checklist.py`, `security_scan.py`). Adopting Python as the core stack avoids ecosystem fragmentation.
5. **Hexagonal Architecture Compatibility:** While Python lacks native structural interfaces like TypeScript, it is entirely capable of maintaining strict application boundaries through `typing.Protocol` (structural subtyping) or `abc.ABC` (nominal subtyping).

### Rejected Options

**TypeScript / Node.js** was seriously considered and initially recommended. It was rejected **not** because it is technically incapable, but because its strongest advantages (compile-time structural typing, fast I/O event loop, and potential full-stack JavaScript symmetry) do not outweigh Python's runtime validation speed, AI ecosystem dominance, and existing repository alignment for the *currently defined system scope*.

Arguments rejected during the Red Team review:

- *TypeScript is required for massive I/O:* Rejected because the MVP's newsroom volume does not demand Node.js over FastAPI.
- *TypeScript is required because of BullMQ:* Rejected because queue technology is a downstream decision; Python possesses lightweight alternatives (e.g., TaskIQ, Procrastinate) that do not necessarily require Redis/Celery.

## Consequences

### Positive

- **First-Class AI Support:** Day-one access to new features from major LLM providers.
- **Robust Boundary Security:** Highly performant, deterministic data sanitization at the system's edge using Pydantic.
- **Unified Repository Ecosystem:** Development, CI/CD, and the application itself will share a single language ecosystem (Python, managed by `uv`).

### Negative / Trade-offs

- **Domain Modeling Discipline:** Implementing pure Ports and Adapters requires more discipline in Python compared to TypeScript. Developers must strictly adhere to `typing.Protocol` or Abstract Base Classes to enforce domain isolation.
- **Static Analysis Flexibility:** Python's type checkers (MyPy/Pyright) are powerful but occasionally less flexible than TypeScript's type system for extremely complex generic structures.

## Related Documents

- `docs/ENGINEERING_CONSTITUTION.md`
- `docs/SDD.md` (Software Design Document v1.1.0)
- `docs/adr/ADR-001-Analysis.md` (Original Proposal)
- `docs/adr/ADR-001-RedTeam.md` (Adversarial Audit)
- `docs/adr/ADR-001-Reconciliation.md` (Reconciliation Brief)
