---
adr-id: ADR-002
title: Persistence & Transactional State Strategy
status: PROPOSED FOR HUMAN DECISION
related-documents:
  - docs/ENGINEERING_CONSTITUTION.md
  - docs/PRD.md
  - docs/SDD.md
  - docs/adr/ADR-001-Runtime-Language.md
---

# ADR-002 Analysis — Persistence & Transactional State Strategy

## 1. Purpose

Define the persistence strategy and transactional architecture required to support the JincSAE's critical invariants: transactional integrity, explicit workflow state, editorial traceability, concurrency safety, idempotency, auditability, and operational simplicity—without introducing infrastructure complexity that the MVP does not require.

This is an **analysis artifact**. It is `PROPOSED FOR HUMAN DECISION` and must not be treated as an accepted or locked decision.

---

## 2. Decision Context

The JincSAE is a Python-based (ADR-001: Accepted) backend automation engine that transforms WordPress-published articles into platform-specific social media content through a multi-stage, human-supervised pipeline.

The persistence layer must support the following domain lifecycle:

```
Article
    └── EditorialBrief
            └── ContentVersion (1..N)
                    ├── ValidationResult
                    ├── ApprovalDecision
                    └── PublicationAttempt (1..N)
```

All transitions between domain states must be explicit, persistent, recoverable, and auditable. Content generation and content publication are architecturally separated concerns.

---

## 3. Authoritative Constraints

Derived directly from the `Engineering Constitution` and the accepted `SDD v1.1.0`. These are **non-negotiable**.

| Constraint | Source | Implication for Persistence |
| :--- | :--- | :--- |
| Article is the canonical factual source | Constitution | Persistence must link all derivative data back to the originating Article. |
| LLM output is untrusted until validated | Constitution + SDD §12 | The schema must distinguish between `raw_generation` and `validated_content`. |
| Explicit, traceable state transitions | Constitution + SDD §10 | State changes must be persisted atomically with an auditable timestamp and actor. |
| Human authority is attributable | Constitution + SDD §10 | Approval actions must record `editor_id`, `timestamp`, `from_state`, `to_state`, and `reason`. |
| Generation and Publication are separate | SDD §6 | These must not be collapsed into a single, opaque table record. |
| Concurrency-safe idempotency | SDD §11 | Duplicate webhook delivery must not corrupt the system state. |
| Regeneration creates a new ContentVersion | SDD §10 | Regeneration is not a state rollback; it is a new entity linked to the same Brief. |
| PublicationAttempt is a distinct traceable record | SDD §10 | Publication retries must produce immutable attempt records, not overwrite state. |

---

## 4. Persistence Problems to Solve

### A. Article Identity and Deduplication

How should the system identify a WordPress article to prevent duplicate ingestion?

**Analysis:**

- The WordPress `post_id` is stable for a given article, but not globally unique across installations.
- A `canonical_url` is stable and human-meaningful, but may change with slug changes.
- A `content_hash` detects semantic changes in the article body but requires hashing at ingestion time.
- An internal `JincSAE UUID` isolates the domain from WordPress coupling, but requires a correlation table.

**Architectural Judgment:** A compound uniqueness strategy is likely needed: use the WordPress `post_id` + a configured `source_id` (representing the installation) as the external key, plus an internal `Article UUID` for domain identity. A database unique constraint on `(source_id, wp_post_id)` prevents duplicate ingestion.

### B. Idempotent Ingestion

WordPress and upstream systems may send duplicate, delayed, out-of-order, or concurrent webhook events.

**Mechanisms under analysis:**

| Mechanism | Guarantees | Trade-offs |
| :--- | :--- | :--- |
| Unique constraint on `(source_id, wp_post_id)` | Prevents duplicate article records | Does not handle concurrent identical requests gracefully without explicit handling |
| `INSERT ... ON CONFLICT DO NOTHING` (Upsert) | Atomic deduplication at the DB level | Returns ambiguous success; requires application-level detection of "already exists" |
| Idempotency key in request + lookup before insert | Stateful deduplication | Requires an `IdempotencyRecord` table; adds a read before every write |
| Optimistic concurrency with version check | Safe for updates, not initial creation | Not effective for creation deduplication |

**Recommendation direction (preliminary):** Unique database constraint on the article external identifier, combined with an `ON CONFLICT` strategy at the application layer. This is simple, correct, and survives crashes without distributed locks.

### C. Content Versioning

Regeneration is a business event, not a state rollback. The SDD explicitly mandates this.

**Mechanisms under analysis:**

| Strategy | Description | Trade-offs |
| :--- | :--- | :--- |
| Mutable single record | Overwrite the content; no history | ❌ Loses history. Violates traceability constraint. |
| Revision chain (linked list) | Each version points to previous | Queries become complex; good for linear history |
| Immutable versions (append-only, sorted) | New row per version, version number column | ✅ Simple, queryable, traceability is trivial |
| Event Sourcing (reconstruct from events) | All state derived from events | Powerful but significant added complexity for MVP |

**Architectural Judgment:** Immutable, append-only `ContentVersion` records with a `version_number` per `(brief_id, platform)` pair is the simplest strategy that satisfies the traceability constraint. The "current" version is always the one with the highest `version_number` for a given brief/platform combination.

### D. Workflow State Persistence

The SDD defines the following lifecycle states: `GENERATED → VALIDATED → PENDING_REVIEW → APPROVED → REJECTED → EDITED → SCHEDULED → PUBLISHED → PUBLISH_FAILED`.

Critical transitions that must be atomic:

- `GENERATED → VALIDATED` (after validation passes)
- `PENDING_REVIEW → APPROVED/REJECTED` (human action; must record actor)
- `APPROVED → SCHEDULED` (scheduling commitment)
- `SCHEDULED → PUBLISHED` (after platform confirmation + external ID stored)

**Concurrency control for state transitions:**

| Strategy | Description | Appropriate for |
| :--- | :--- | :--- |
| Optimistic concurrency (version column) | Read version, update WHERE version = N, check rows affected | Multiple readers; infrequent conflicts |
| Pessimistic locking (SELECT FOR UPDATE) | Lock row during a transaction | High contention; short critical sections |
| Compare-and-swap via conditional UPDATE | `UPDATE ... SET status = 'X' WHERE status = 'Y'` | State machine transition guards |

**Architectural Judgment:** A `compare-and-swap` conditional `UPDATE` is the most practical strategy for a single-node Python application. `UPDATE content_versions SET status = 'VALIDATED' WHERE id = $1 AND status = 'GENERATED'` is atomic at the database level and does not require distributed locks. If `rows_affected = 0`, a conflict has occurred and must be handled.

### E. Publication Idempotency

> The most dangerous persistence failure is publishing the same content twice.

The database alone cannot guarantee exactly-once delivery to external platforms. The analysis must be explicit about what guarantees are realistically achievable.

| Guarantee | Achievable? | Notes |
| :--- | :--- | :--- |
| Exactly Once (to the social platform) | ❌ No | External APIs are not transactionally coordinated with the local DB |
| At Least Once | ✅ Yes | With retries; requires idempotent handling at the recipient or external ID check |
| At Most Once | ✅ Yes | Without retries; accept potential loss |
| Effectively Once | ✅ Yes (target) | At-least-once with duplicate detection using external platform IDs |

**Target strategy: Effectively Once.**

The `PublicationAttempt` record acts as the deduplication anchor. Before a new publication attempt is dispatched, the system checks if any attempt for this `ContentVersion` has `status = PUBLISHED` with a valid `external_publication_id`. If so, it is skipped. A `SCHEDULED` state prevents concurrent publication workers from claiming the same content without explicit state transition.

### F. Auditability

The persistence layer must be able to answer the following editorial and operational audit questions:

- Which article produced this post?
- Which `ContentVersion` was approved?
- Who approved it, when, and with what reason?
- How many publication attempts were made for a given post?
- Which external post ID was returned by the platform?
- What was the failure reason for a failed attempt?

All of these questions are satisfiable with relational persistence if the schema is designed intentionally.

---

## 5. Architectural Invariants

Derived from constraints and problem analysis, the following invariants are non-negotiable regardless of the chosen persistence strategy:

1. Every `ContentVersion` must trace to an `EditorialBrief` which traces to an `Article`.
2. Every `ApprovalDecision` must record `actor_id`, `timestamp`, `from_state`, `to_state`.
3. Every `PublicationAttempt` is immutable once created; only its `status`, `external_id`, and `failure_reason` may be updated (not deleted or overwritten).
4. Duplicate article ingestion must be handled by the persistence layer (unique constraint), not by application-level coordination.
5. State transitions must be conditional (compare-and-swap) to prevent race conditions.
6. Regeneration must create a new `ContentVersion`; it must not modify or delete an existing version.

---

## 6. Candidate Strategies

### OPTION A — Relational Database (PostgreSQL)

**Overview:** Use a single PostgreSQL instance as the primary persistence store, organized around a relational schema that mirrors the domain's entity relationships and state machine.

**Relevant Capabilities:**

- **ACID Transactions:** Atomic multi-table writes (e.g., create `ContentVersion` + update `Article` state in one transaction). (FACT)
- **Foreign Keys & Constraints:** Enforce relational integrity at the database level. (FACT)
- **Unique Constraints:** Concurrency-safe deduplication without application-level locking. (FACT)
- **`FOR UPDATE` and conditional UPDATE:** Native pessimistic and optimistic concurrency control. (FACT)
- **JSONB columns:** Store unstructured LLM output alongside structured domain data without a separate document store. (FACT)
- **`pg_notify` / Advisory Locks:** Can serve as simple background job signaling (Procrastinate uses this). (FACT)
- **Python ecosystem:** SQLAlchemy 2.x, asyncpg, SQLModel, Alembic are all mature and well-supported. (FACT)

**Gaps / Risks:**

- Schema migrations require discipline (Alembic or equivalent).
- No built-in immutable audit log; must be designed into the schema.

### OPTION B — Document-Oriented Database (MongoDB)

**Overview:** Use MongoDB as the primary store, leveraging document flexibility to store nested content structures.

**Analysis:**

- **Content Versioning:** A document can embed version history as an array, making versioning natural. (SUPPORTED INFERENCE)
- **Transactions:** MongoDB supports multi-document ACID transactions since v4.0, but they are not as performant or natural as PostgreSQL transactions. (FACT)
- **Audit Trails:** Audit history can be embedded in documents, but cross-document audit queries become complex. (ARCHITECTURAL JUDGMENT)
- **Relational Queries:** Joining data across collections (e.g., Article → Brief → ContentVersion → ApprovalDecision) requires application-level joins or `$lookup`, which are less expressive and performant than SQL JOINs. (FACT)
- **Unique Constraints:** Available at the collection level, but compound constraints spanning concepts are harder to enforce. (FACT)
- **Python ecosystem:** `Motor` (async MongoDB driver) is mature, but the lack of a schema enforcement layer comparable to Pydantic + SQLAlchemy means boundary enforcement must be done entirely in the application layer. (ARCHITECTURAL JUDGMENT)

**Verdict for JincSAE:** The system's defining characteristic is the explicit relational chain Article → Brief → Version → Approval → Publication. This is a fundamentally relational data model with multi-entity transactions. MongoDB's strength is flexible schema and document nesting; its weaknesses (cross-collection joins, transaction performance, weaker relational integrity) directly target the JincSAE's most critical requirements. Its use is not impossible, but it adds complexity where the relational model would be straightforward.

### OPTION C — Event Sourcing / Event Store

**Overview:** Store all state as a sequence of immutable domain events (e.g., `ArticleIngested`, `ContentGenerated`, `ContentApproved`, `PublicationAttempted`). Current state is derived by replaying events.

**Advantages:**

- Complete and automatic audit trail. (FACT)
- State is reconstructible at any point in time. (FACT)
- Temporal queries ("what was the state of this content on day X?") are trivially answerable. (FACT)
- Explicit domain events match the SDD's explicit state transition model. (ARCHITECTURAL JUDGMENT)

**Risks:**

- Significant increase in operational complexity: event schema evolution, snapshot management, projection consistency. (FACT)
- Querying current state requires projections (read models) which must be kept synchronized. (FACT)
- Debugging is harder: the state at any point must be reconstructed by event replay. (ARCHITECTURAL JUDGMENT)
- Strong overengineering risk for MVP: The PRD does not evidence requirements for temporal queries or advanced event replay. (ARCHITECTURAL JUDGMENT)
- Team learning curve is high; the pattern is non-trivial to implement correctly in Python. (ARCHITECTURAL JUDGMENT)

**Red Team Preemption:** Do not adopt Event Sourcing merely because auditability is a requirement. State-transition history tables (Option D approach) provide auditability at a fraction of the complexity.

**Verdict:** Event Sourcing is architecturally elegant but not justified by the evidence in the PRD or SDD for the MVP. It should be **evaluated and rejected** at this stage, with the explicit note that the architecture must not preclude adding event-driven projections later if requirements evolve.

### OPTION D — Hybrid: Relational State + Transition History Table

**Overview:** PostgreSQL as the primary state store, with a dedicated `state_transitions` table that acts as a structural audit log for critical entity state changes.

This is not a "two-database" hybrid—it is a single PostgreSQL instance where some tables serve current-state queries and a specific `state_transitions` table serves audit and history queries.

**Structure conceptually:**

```
content_versions         (current state, mutable via CAS)
state_transitions        (append-only, never modified)
publication_attempts     (append-only, status fields updated)
```

**Benefits:**

- `state_transitions` provides an auditable, queryable history of all `APPROVED`, `REJECTED`, `REGENERATED` events without the complexity of Event Sourcing.
- Current state queries remain simple and fast (single table read).
- Audit queries are natural SQL.
- Still a single PostgreSQL instance; operational simplicity preserved.

---

## 7. Transaction Boundary Analysis

| Operation | Must Be Atomic | Can Be Async | Must Survive Crash | Must Not Happen Twice |
| :--- | :---: | :---: | :---: | :---: |
| Ingest Article | ✅ Yes | No | ✅ Yes | ✅ Yes |
| Create Editorial Brief | ✅ Yes | Partially | ✅ Yes | ✅ Yes |
| Create ContentVersion | ✅ Yes | Partially | ✅ Yes | No |
| Record Validation Result | ✅ Yes | No | ✅ Yes | No |
| Transition to PENDING_REVIEW | ✅ Yes | No | ✅ Yes | ✅ Yes |
| Approve Content | ✅ Yes | No | ✅ Yes | ✅ Yes |
| Claim Content for Scheduling | ✅ Yes | No | ✅ Yes | ✅ Yes |
| Record PublicationAttempt | ✅ Yes | No | ✅ Yes | No (retry = new attempt) |
| Update Attempt with Platform ID | ✅ Yes | No | ✅ Yes | ✅ Yes |

**Key insight:** The `Claim Content for Scheduling` operation is the system's most critical transaction boundary. Before dispatching a publication job, the application must atomically transition the `ContentVersion` from `APPROVED` to `SCHEDULED` using a conditional UPDATE. If the process crashes after scheduling but before the platform call, the background worker should detect the stuck `SCHEDULED` state and safely retry (creating a new `PublicationAttempt`).

---

## 8. Concurrency Analysis

### Scenario 1: Two Identical WordPress Webhooks Arrive Simultaneously

- **Risk:** Duplicate `Article` records; duplicate pipeline execution for the same post.
- **Persistence Mechanism:** Unique database constraint on `(source_id, wp_post_id)`. Only one `INSERT` succeeds; the other receives a unique constraint violation.
- **Consistency Requirement:** The application must handle the constraint violation gracefully and return a success response (idempotent behavior).
- **Residual Risk:** Very low. The first transaction commits; the second is rejected at the DB level. No data corruption possible.

### Scenario 2: Two Editorial Users Approve or Reject the Same ContentVersion

- **Risk:** Double-approval; conflicting decisions overwrite each other.
- **Persistence Mechanism:** Compare-and-swap: `UPDATE content_versions SET status = 'APPROVED' WHERE id = $1 AND status = 'PENDING_REVIEW'`. The second concurrent update finds `status ≠ PENDING_REVIEW` and affects 0 rows.
- **Consistency Requirement:** Application must check `rows_affected` and raise a conflict error to the second user.
- **Residual Risk:** Low. One decision wins; the other is explicitly rejected with a detectable error.

### Scenario 3: A Retry Worker and Manual User Interact with the Same Publication Record

- **Risk:** Double publication; the worker starts publishing while a user manually retries.
- **Persistence Mechanism:** `SCHEDULED` state acts as an exclusive claim. Transitioning from `APPROVED → SCHEDULED` must be atomic and conditional. Only the entity that performs the CAS transition can proceed to publication.
- **Consistency Requirement:** Both the worker and the manual trigger must go through the same CAS transition.
- **Residual Risk:** Moderate. If the system crashes after the platform API is called but before the DB is updated, the `SCHEDULED` content must be detected as "stuck" and retried. A new `PublicationAttempt` must be created; the external platform may have already received the first call. This is where `external_publication_id` becomes critical for deduplication.

### Scenario 4: Application Crashes After External API Call But Before Recording Result

- **Risk:** Content is published on the platform, but the JincSAE has no record of it. On restart, a retry creates a second publication.
- **Persistence Mechanism:** The background worker must first atomically claim the `ContentVersion` (CAS to `SCHEDULED`), then call the external API, then update the `PublicationAttempt` with the `external_publication_id`. On crash recovery, the worker detects the stuck `SCHEDULED` state and creates a new `PublicationAttempt`. It must first check if a prior attempt for this content already has an `external_publication_id` (meaning it was likely published).
- **Consistency Requirement:** The architecture must accept "at least once" for external calls and mitigate via `external_publication_id` check.
- **Residual Risk:** Low-to-moderate. Not eliminable without two-phase commit against the external platform (impossible). The `external_publication_id` check is the practical mitigation.

### Scenario 5: A Publication Job Is Delivered More Than Once

- **Risk:** The background job system delivers the same publication task twice.
- **Persistence Mechanism:** The same CAS mechanism protects against this. The first delivery transitions the state to `SCHEDULED`. The second delivery finds the state is already `SCHEDULED` or `PUBLISHED` and exits without action.
- **Residual Risk:** Very low with the CAS guard.

---

## 9. Idempotency Analysis

Two classes of idempotency must be addressed:

**Class 1: Ingestion Idempotency** (Webhook deduplication)

- Mechanism: Unique DB constraint on `(source_id, wp_post_id)`.
- Application behavior: Catch the DB uniqueness violation; return success (the article exists).
- Evidence level: FACT — This is a standard, well-proven pattern.

**Class 2: Publication Idempotency** (Preventing duplicate posts)

- Mechanism: CAS state transition (`APPROVED → SCHEDULED`) + `external_publication_id` check on retry.
- Application behavior: Before publishing, query if any prior `PublicationAttempt` for this `ContentVersion` already has a non-null `external_publication_id`. If yes, skip.
- Evidence level: ARCHITECTURAL JUDGMENT — This achieves "effectively once" semantics, not "exactly once", which is the practical maximum achievable without transactional coordination with the external platform.

---

## 10. Publication Side-Effect Analysis

The database cannot transactionally control external API calls to LinkedIn, Instagram, Facebook, or Bluesky. Therefore, the architecture must distinguish:

| Boundary | Controllable by DB? | Mechanism |
| :--- | :---: | :--- |
| Creating PublicationAttempt record | ✅ Yes | Standard INSERT |
| Calling the social platform API | ❌ No | External HTTP call |
| Recording the external platform's response | ✅ Yes | UPDATE on PublicationAttempt |

**Transactional Outbox Pattern consideration:**
A full Transactional Outbox would atomically write the publication intent to a DB table and have a separate worker poll and dispatch it. This eliminates the crash window between DB write and external call.

**MVP Justification Assessment:** The Outbox adds significant infrastructure complexity. For the MVP, the simpler approach (CAS claim + try/catch + PublicationAttempt record) is sufficient, provided the architecture explicitly acknowledges the at-least-once semantics and implements the `external_publication_id` guard. The Outbox should be noted as a future evolution path if publication volume or reliability requirements increase.

**Preliminary verdict:** Do not implement a Transactional Outbox for the MVP. Mark it as a `Future Evolution` candidate.

---

## 11. Auditability Analysis

### Approach A: Audit Columns (`created_at`, `updated_at`, `created_by`)

- **Scope:** Minimum viability. Records who created or last modified a record.
- **Limitation:** Cannot reconstruct history; previous states are lost on UPDATE.
- **Verdict:** Necessary but insufficient for JincSAE's editorial accountability requirements.

### Approach B: State Transition History Table

A dedicated `state_transitions` table that is append-only:

```
state_transitions:
  id             UUID PK
  entity_type    TEXT ('content_version', 'publication_attempt')
  entity_id      UUID FK
  from_state     TEXT
  to_state       TEXT
  actor_id       TEXT
  timestamp      TIMESTAMPTZ
  reason         TEXT (optional)
  metadata       JSONB (optional)
```

- **Scope:** Captures every critical state change with actor, time, and reason.
- **Auditability:** Satisfies all audit questions identified in Section 4.F.
- **Complexity:** Low. A single append-only table, inserted within the same transaction as the state change.
- **Evidence level:** FACT — This is a proven and well-understood pattern in PostgreSQL applications.
- **Verdict:** ✅ Recommended approach for the MVP.

### Approach C: Full Event Sourcing

Already analyzed in Section 6, Option C. Rejected for MVP due to operational complexity not justified by current requirements.

---

## 12. Data Access Strategy Analysis

Given ADR-001 (Python), the following data-access options are evaluated:

### SQLAlchemy 2.x (Core + ORM)

- **Async Support:** ✅ Via `asyncio` extension with `asyncpg` driver. (FACT)
- **Type Safety:** ✅ Mapped columns and typed models compatible with Mypy/Pyright. (FACT)
- **Transaction Control:** ✅ Explicit session/unit-of-work; async context manager for transactions. (FACT)
- **Migrations:** ✅ Alembic is the de-facto companion. (FACT)
- **Domain Isolation:** ⚠️ ORM models can leak into domain if not behind a Repository/Mapper layer. Requires discipline.
- **Operational Transparency:** ✅ `echo=True` logs all SQL; query plans accessible via `EXPLAIN`.

### SQLModel

- **Description:** SQLAlchemy + Pydantic hybrid. Model classes are simultaneously Pydantic models and SQLAlchemy mapped classes.
- **Strength:** Reduces boilerplate for simple CRUD; Pydantic validation on data model.
- **Risk:** Collapses domain model and persistence model into the same class. This violates the SDD's Hexagonal Architecture principle of domain independence if used naïvely.
- **Evidence level:** ARCHITECTURAL JUDGMENT — SQLModel is appropriate when domain and persistence models are intentionally aligned (e.g., CRUD APIs). For JincSAE's DDD-leaning architecture, it introduces coupling risk.

### Raw SQL / Async Driver (asyncpg)

- **Strength:** Maximum control; no ORM overhead; queries are explicit.
- **Risk:** More boilerplate; type safety must be maintained manually; migrations require explicit SQL scripting or an external tool.
- **Appropriate when:** Performance-critical queries where ORM overhead matters, or for teams with deep SQL expertise.

### Repository Abstraction

The SDD mandates Ports and Adapters. The persistence layer must implement a `RepositoryPort` (interface) that the application layer calls. The SQLAlchemy adapter implements the port.

- **Recommendation:** Repository pattern is appropriate here, but should be kept **pragmatic**. Do not create a generic `Repository[T]` hierarchy or abstract base for every entity. Define concrete port interfaces (`ArticleRepository`, `ContentVersionRepository`) per aggregate, with only the methods actually needed by use cases.
- **Evidence level:** ARCHITECTURAL JUDGMENT.

---

## 13. Decision Drivers

The following independent drivers are relevant to the JincSAE persistence decision:

| Driver | Weight | Justification |
| :--- | :---: | :--- |
| Transactional Integrity | Critical | Multi-entity workflows require atomic state transitions. |
| Concurrency Safety | Critical | Multiple processes (workers, users, retries) interact with the same records. |
| Traceability | Critical | Constitutional requirement: full chain Article → PublicationAttempt must be queryable. |
| Idempotency Support | High | Webhook deduplication and publication exactly-once are architectural requirements. |
| Auditability | High | Editorial accountability requires state transition history with actor attribution. |
| Python Ecosystem Compatibility | High | Stack is Python (ADR-001). ORM and tooling must be mature. |
| Operational Simplicity | High | MVP must not introduce unnecessary infrastructure services. |
| Content Versioning Support | High | Regeneration model requires append-only versioning. |
| External Side-Effect Recovery | Medium | Crash recovery for publication must be handled gracefully. |
| Migration Support | Medium | Schema evolution must be structured and reversible. |
| Reversibility | Medium | The persistence choice should not preclude future evolution. |

**Drivers removed for duplication/invalidity:**

- ~~Scalability:~~ Not evidenced in PRD for MVP. (Scale Inflation check passed)
- ~~Cost:~~ Deployment context not specified; both Mongo and Postgres have free tiers.
- ~~Developer Experience (as standalone driver):~~ Subsumed by Python Ecosystem Compatibility and Operational Simplicity.

---

## 14. Decision Matrix

| Driver | Weight | Option A: PostgreSQL | Option B: MongoDB | Option C: Event Sourcing | Option D: PostgreSQL + Hybrid Audit |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Transactional Integrity | Critical | ✅ 5 | ⚠️ 3 | ⚠️ 3 | ✅ 5 |
| Concurrency Safety | Critical | ✅ 5 | ⚠️ 3 | ✅ 4 | ✅ 5 |
| Traceability | Critical | ✅ 4 | ⚠️ 3 | ✅ 5 | ✅ 5 |
| Idempotency Support | High | ✅ 5 | ⚠️ 3 | ✅ 4 | ✅ 5 |
| Auditability | High | ⚠️ 3* | ⚠️ 3 | ✅ 5 | ✅ 5 |
| Python Ecosystem | High | ✅ 5 | ✅ 4 | ✅ 4 | ✅ 5 |
| Operational Simplicity | High | ✅ 5 | ✅ 4 | 🔴 2 | ✅ 5 |
| Content Versioning | High | ✅ 5 | ✅ 4 | ✅ 5 | ✅ 5 |
| Side-Effect Recovery | Medium | ✅ 4 | ✅ 3 | ✅ 4 | ✅ 4 |
| Migration Support | Medium | ✅ 5 | ⚠️ 3 | ⚠️ 3 | ✅ 5 |
| Reversibility | Medium | ✅ 4 | ✅ 4 | 🔴 2 | ✅ 4 |

*PostgreSQL alone (Option A) scores 3 on Auditability because it requires intentional design (the audit table) to satisfy requirements; it is not automatic.

**Option D (PostgreSQL + State Transition History) effectively subsumes Option A** by adding the audit dimension. It does not add operational complexity (same DB) and directly addresses the gap in plain Option A.

---

## 15. Counterfactual Architectures

### Counterfactual A — PostgreSQL (Pure Relational)

**Architecture:**

- State: `articles`, `editorial_briefs`, `content_versions`, `validation_results`, `approval_decisions`, `publication_attempts` tables.
- Versioning: Append-only rows in `content_versions` with `version_number`.
- Concurrency: Conditional UPDATE (`WHERE status = 'X'`) for state transitions.
- Auditability: `created_at`, `updated_at`, `actor_id` columns on critical tables; no formal history table.
- Python Data Access: SQLAlchemy 2.x with `asyncpg`; Repository pattern per aggregate.
- Migrations: Alembic.

**Gap:** Audit queries like "what states did this ContentVersion pass through?" require either reading a current status column (only shows current state) or reconstructing from `updated_at` timestamps (fragile, lossy).

### Counterfactual B — Document Database (MongoDB)

**Architecture:**

- Article document contains embedded `editorial_briefs` with embedded `content_versions`.
- Publication attempts stored as embedded arrays within content documents.
- Audit history embedded as sub-documents.

**Challenges:**

- Cross-document ACID transactions required for multi-entity state changes (e.g., approve content + create audit record). Possible in MongoDB 4+, but adds complexity.
- Query patterns like "find all ContentVersions PENDING_REVIEW across all Articles" require collection-wide scans with inefficient `$unwind` on embedded arrays.
- Unique constraint on `(source_id, wp_post_id)` is achievable but less natural than in PostgreSQL.
- This architecture would need to be designed differently: denormalize significantly and accept some duplication, or normalize and accept MongoDB's join limitations.

### Counterfactual C — Event Sourced

**Architecture:**

- Event store: `domain_events` table (event_id, stream_id, event_type, payload JSONB, timestamp, sequence).
- Read projections: Separate tables reconstructed by event handlers (e.g., `content_version_current_state`).
- Publication: `PublicationAttemptRequested` event triggers outbox worker.

**How it would work:**
`ArticleIngested → EditorialBriefCreated → ContentVersionGenerated → ContentVersionValidated → ContentVersionApprovedByHuman → ContentVersionScheduled → PublicationAttempted → PublicationSucceeded`

**Why it is not recommended for MVP:**

- Projections must be kept synchronized with the event store; eventual consistency introduces complexity.
- Event schema evolution requires careful versioning from day one.
- Zero additional benefit over the Hybrid approach for the current PRD requirements.
- Operational debugging requires event replay tooling.
- ARCHITECTURAL JUDGMENT: The pattern's power (temporal queries, complete audit) is already well-served by a state transition history table at 20% of the complexity.

---

## 16. Reversibility Analysis

| Option | Reversibility | Notes |
| :--- | :--- | :--- |
| PostgreSQL (A or D) | Moderately Reversible | Migrating to another DB requires rewriting ORM models and migrations. The domain layer is protected by the Repository port, limiting the blast radius. |
| MongoDB | Moderately Reversible | Moving to relational would require schema redesign; document → table mapping is non-trivial. |
| Event Sourcing | Expensive to Reverse | Event schema becomes the core contract; migrating away requires replaying all events into a new model. |

**PostgreSQL (Options A/D) provides the best reversibility** for this project, given the Repository port abstraction established in the SDD.

---

## 17. Risks and Trade-offs

| Risk | Option | Severity | Mitigation |
| :--- | :--- | :---: | :--- |
| Schema migration errors break production | PostgreSQL | Medium | Alembic with `--sql` mode for reviewed migrations; staging environment |
| ORM leakage into domain | All relational options | Medium | Explicit Repository port; SQLAlchemy models in the `infrastructure` layer only |
| State transition race condition | All options | High | Mandatory CAS conditional UPDATE; check `rows_affected` |
| Double publication | All options | Critical | `external_publication_id` guard; `SCHEDULED` state as exclusive claim |
| Audit table neglect (data not written) | Option D | Medium | State transition table must be written within the same transaction as the state change |

---

## 18. Open Questions

| Question | Why It Matters | Influences | Blocks Decision? |
| :--- | :--- | :--- | :---: |
| Will a Postgres-backed queue (Procrastinate) be used for background jobs? | If yes, Postgres serves double duty as DB + queue, simplifying infrastructure significantly. | Queue ADR (ADR-003 or similar) | No |
| Expected concurrent editorial users? | Informs whether `SELECT FOR UPDATE` pessimistic locking is needed vs. CAS optimistic. | Concurrency strategy | No — CAS is safe regardless; this is about UX error message quality. |
| Multi-tenant or single-newsroom deployment for MVP? | Multi-tenant adds complexity to the `source_id` / `(source_id, wp_post_id)` uniqueness strategy | Schema design | No — single-newsroom is the safe default |

---

## 19. Preliminary Architectural Recommendation

> **PRELIMINARY — PROPOSED FOR HUMAN DECISION**

The analysis strongly indicates that **Option D (PostgreSQL as primary state store + State Transition History table as audit mechanism)** is the most appropriate persistence strategy for the JincSAE MVP.

**Reasoning:**

1. The domain's defining characteristic—a relational chain of entities with explicit state transitions—maps naturally and efficiently onto a relational model. (FACT)
2. PostgreSQL's ACID transactions, unique constraints, and conditional UPDATE provide all the concurrency safety mechanisms the system requires without introducing distributed infrastructure. (FACT)
3. The state transition history table satisfies all auditability requirements at minimal operational cost (same DB, append-only writes within the same transactions). (ARCHITECTURAL JUDGMENT)
4. This approach preserves the SDD's Hexagonal Architecture: SQLAlchemy models live in the `infrastructure` layer and are exposed to the application layer only through Repository ports. (ARCHITECTURAL JUDGMENT)
5. Operational simplicity is maximized: one database, one migration tool (Alembic), one Python ORM (SQLAlchemy 2.x), no additional infrastructure services required. (ARCHITECTURAL JUDGMENT)

**Rejected approaches and reasons:**

- **MongoDB:** Relational integrity requirements and multi-entity transactions make the document model a poor fit. (ARCHITECTURAL JUDGMENT)
- **Event Sourcing:** The auditability requirements are fully satisfiable with a transition history table. Event Sourcing adds significant complexity without demonstrated benefit for the MVP PRD. (ARCHITECTURAL JUDGMENT)
- **Transactional Outbox:** Not required for MVP; effectively-once semantics via `external_publication_id` guard is sufficient. Marked as future evolution. (ARCHITECTURAL JUDGMENT)

**Data Access:** SQLAlchemy 2.x (async) with `asyncpg` driver. Repository interfaces defined per aggregate in the Application layer. Migrations via Alembic.

---

## 20. Human Decision Required

This document is `PROPOSED FOR HUMAN DECISION`. The following verification checklist is provided for the Architecture Review and Red Team phases before acceptance:

```
[x] Authoritative documents inspected (Constitution, PRD, SDD, ADR-001)
[x] Accepted SDD preserved — no contradictions introduced
[x] ADR-001 preserved — no language re-evaluation
[x] No database chosen merely by preference or convention
[x] Transaction boundaries explicitly analyzed
[x] Concurrency scenarios analyzed (5 scenarios)
[x] Idempotency analyzed (2 classes)
[x] External side effects distinguished from DB transactions
[x] Exactly-once guarantees not falsely claimed
[x] Auditability approaches compared (3 approaches)
[x] Event Sourcing evaluated fairly and explicitly rejected with rationale
[x] No premature infrastructure implementation
[x] No duplicate decision drivers
[x] No circular reasoning (no queue technology used to justify DB choice)
[x] Scale assumptions supported by evidence (or explicitly not evidenced)
[x] Evidence and architectural judgment separated throughout
[x] Open questions explicitly classified
[x] Human decision remains required
```
