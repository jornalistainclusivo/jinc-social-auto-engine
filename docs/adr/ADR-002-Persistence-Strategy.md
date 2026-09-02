# ADR-002: Persistence & Auditability Strategy

## Status

**Accepted**

## Decision Process

This ADR is the product of a formal four-phase architectural review:

| Phase | Artifact | Outcome |
| :--- | :--- | :--- |
| Analysis | `ADR-002-Analysis.md` | Preliminary recommendation: Option D (PostgreSQL + Hybrid Audit) |
| Architecture Review | `ADR-002-ArchReview.md` | Conditional — 4 findings requiring resolution |
| Red Team | `ADR-002-RedTeam.md` | Holds with Material Revisions — 5 required corrections |
| Reconciliation | `ADR-002-Reconciliation.md` | Corrected architecture; 2 genuine human decisions identified |
| Decision Readiness | `ADR-002-Decision-Readiness.md` | READY WITH DECISION REFINEMENT — 5 items reduced to 2 true decisions |

**Human Decision declared:** 2026-08-31  
**Decision 1 — Persistence & Auditability Strategy:** APPROVED  
**Decision 2 — External Publication Risk Acceptance:** ACCEPTED

---

## Context

The JincSAE is a Python-based (ADR-001: Accepted) editorial automation backend that transforms WordPress-published articles into platform-specific social media content through a multi-stage, human-supervised pipeline.

The persistence layer must support the following domain lifecycle:

```
Article
    └── EditorialBrief
            └── ContentVersion (1..N per platform)
                    ├── ValidationResult
                    ├── ApprovalDecision
                    └── PublicationAttempt (1..N)
```

Every transition between domain states must be: explicit, persistent, recoverable, attributable, and auditable. Content generation and content publication are architecturally separated concerns (Engineering Constitution §13, SDD §6).

### Authoritative Constraints (Non-Negotiable)

These constraints are derived from the Engineering Constitution and accepted SDD v1.1.0. They are not decisions — they are inherited architectural invariants:

| Constraint | Source | Persistence Implication |
| :--- | :--- | :--- |
| Article is the canonical factual source | Constitution §4 | All derivative entities must trace to an Article |
| LLM output is untrusted until validated | Constitution §5, SDD §12 | Schema must separate raw LLM output from validated domain state |
| Explicit, traceable state transitions | Constitution §14, SDD §10 | State changes are atomic units: state update + audit record |
| Human authority is attributable | Constitution §15, SDD §10 | Approval actions must record actor identity, timestamp, from_state, to_state |
| Generation and Publication are separate | Constitution §13, SDD §6 | These must not be collapsed into a single table record |
| Idempotency is mandatory | Constitution §16, SDD §11 | Duplicate webhooks and duplicate job delivery must be handled at the persistence layer |
| Regeneration creates a new ContentVersion | SDD §10 | Regeneration is not a state rollback; it creates a new entity |
| No silent failure | Constitution §15 | Every critical failure must produce an observable persistent state |
| Hexagonal Architecture | SDD §7, §9 | Persistence layer must be behind Repository ports; domain must not import infrastructure |

---

## Decision Drivers

| Driver | Weight | Justification |
| :--- | :---: | :--- |
| Transactional Integrity | Critical | Multi-entity workflows require atomic, durable state changes |
| Auditability with Attributability | Critical | Constitutional requirement: actor + timestamp + state chain must be queryable |
| Concurrency Safety | Critical | Multiple workers, users, and retry processes interact with the same records |
| Idempotency Support | High | Webhook deduplication and publication recovery are architectural requirements |
| Failure Recovery | High | Crashes during publication must leave the system in a deterministic, recoverable state |
| Operational Simplicity | High | The MVP must not introduce unjustified infrastructure services |
| Python Ecosystem Compatibility | High | Stack is Python (ADR-001); data access tooling must be mature |
| Reversibility | Medium | The architecture must not preclude future evolution |

---

## Considered Options

### Option A — PostgreSQL (Pure Relational)

PostgreSQL as the primary store with standard relational tables. Audit is achieved through `created_at`, `updated_at`, `actor_id` columns on entity tables.

**Gap:** Cannot reconstruct state history. "What states did this ContentVersion pass through?" is unanswerable without fragile timestamp inference. Insufficient for the Engineering Constitution's auditability requirement.

### Option B — Document Database (MongoDB)

MongoDB as the primary store, leveraging document nesting for versioning and embedded audit history.

**Gap:** The JincSAE domain is fundamentally relational: Article → Brief → ContentVersion → Approval → Publication. Cross-collection ACID transactions for multi-entity workflows are more complex in MongoDB than in PostgreSQL. Cross-collection queries (e.g., "find all ContentVersions PENDING_REVIEW") require `$lookup` or application-level joins. The relational model is the superior fit for this domain.

### Option C — Event Sourcing

All state derived from an immutable event stream. Current state reconstructed by event replay.

**Genuine benefits acknowledged (Red Team finding):** Structural audit enforcement by architecture; native crash recovery; causal chain queryability.

**Why rejected for MVP:** (1) Projection infrastructure required for current-state queries adds operational complexity not evidenced in the PRD. (2) Event schema versioning must be designed from day one and cannot be retrofitted. (3) The audit enforcement benefit is achievable through mandatory transaction boundary discipline without full Event Sourcing. (4) No PRD requirement evidences the need for temporal state reconstruction or event replay. (5) Complexity is disproportionate to the current scope. Event Sourcing remains a documented future architectural option if compliance requirements evolve.

### Option D — PostgreSQL + Hybrid Audit (Selected)

PostgreSQL as the primary state store. Dedicated append-only audit history tables per aggregate, written within the same database transaction as the state change. A single PostgreSQL instance serves both functions — no second database introduced.

---

## Decision

**PostgreSQL is adopted as the persistence technology for the JincSAE MVP, implementing a Hybrid Audit model (current-state tables + per-aggregate append-only audit history tables).**

---

## Rationale

### 1. Relational Model Is the Natural Fit

The JincSAE domain is defined by an explicit relational chain of entities with multi-step, multi-actor workflows. This model maps directly and efficiently to a relational schema. Cross-entity queries (e.g., "who approved this ContentVersion, and which Article originated it?") are straightforward SQL joins. (FACT)

### 2. PostgreSQL Provides All Required Concurrency Primitives Without Distributed Infrastructure

- **ACID transactions:** Atomic multi-table writes within a single connection.
- **Unique constraints:** Database-enforced deduplication for article ingestion without application-level coordination.
- **Conditional UPDATE (Compare-and-Swap):** Atomic state transition guard: `UPDATE content_versions SET status = 'X' WHERE id = $1 AND status = 'Y'`. If `rows_affected = 0`, the transition was rejected at the database level.
- No distributed locks, no external coordination services required for the MVP. (FACT)

### 3. Hybrid Audit Satisfies Auditability at Minimal Operational Cost

The `state_transitions` append-only history tables provide a queryable record of every critical state change — with actor attribution, timestamp, reason, and state boundary — at the cost of one additional INSERT per transition, within the same transaction. No additional infrastructure service required. (FACT)

### 4. Option D Preserves the SDD's Hexagonal Architecture

SQLAlchemy models live in the `infrastructure` layer and are accessible to the application layer only through Repository port interfaces. The domain layer has no dependency on PostgreSQL or any ORM. (DESIGN DECISION — consistent with SDD §7, §9)

### 5. Operational Simplicity

One database. One migration tool (Alembic). One async ORM (SQLAlchemy 2.x with asyncpg). No secondary stores, no event bus, no projection services for the MVP. (DESIGN DECISION)

---

## Architectural Invariants (Locked)

The following invariants are binding on all implementations. They may not be relaxed by implementation convenience or downstream specifications without a superseding ADR.

### Invariant 1 — Atomic State Transition Unit

The atomic unit of a domain state transition is the pair:

```
(1) CAS conditional UPDATE on the current-state table
+
(2) INSERT into the audit history table for this aggregate
```

Both operations must execute within a single explicit database transaction. An implementation that commits the state change and the audit record in separate database calls, or in separate transactions, violates this invariant and the Engineering Constitution's traceability requirement (Constitution §14).

No state transition is considered complete unless both operations succeed atomically.

### Invariant 2 — Append-Only Audit History

Audit history records are immutable once created. They must not be updated, overwritten, or deleted. Entity records that have associated audit history must use soft-delete (`deleted_at TIMESTAMPTZ`) rather than hard-delete to prevent audit record orphaning.

### Invariant 3 — Content Version Lineage

Every `ContentVersion` must trace through a relational FK chain to its originating `Article`:

```
ContentVersion → EditorialBrief → Article
```

This chain must be enforced by database-level FK constraints, not by application-level convention.

### Invariant 4 — Regeneration Creates a New ContentVersion

Regeneration is a business event, not a state rollback. A regeneration request must create a new `ContentVersion` entity linked to the same `EditorialBrief`. Existing `ContentVersion` records must not be modified or deleted as a result of regeneration. (SDD §10)

### Invariant 5 — PublicationAttempt Is an Immutable Operational Record

Every publication dispatch creates a new `PublicationAttempt` record. These records are append-only: only the `status`, `external_publication_id`, and `failure_reason` fields may be updated after creation. A retry is always a new `PublicationAttempt`, not a modification of an existing one.

### Invariant 6 — CAS as Exclusive State Claim

State transitions must use conditional UPDATE as the primary concurrency guard. All callers — background workers, API handlers, retry mechanisms — must go through the same CAS transition for any given state change. No caller may bypass the CAS guard.

### Invariant 7 — Repository Port Isolation

The domain layer must not import or depend on SQLAlchemy models, database drivers, or any persistence-layer infrastructure. All persistence operations must be invoked through Repository port interfaces defined in the application layer and implemented in the infrastructure layer.

---

## State Machine (Inherited from Engineering Constitution §14)

The Engineering Constitution §14 defines the publication lifecycle state machine. The following states and transitions are constitutionally mandated:

```
GENERATED
    ↓
VALIDATED
    ↓
PENDING_REVIEW
    ├──────────► REJECTED
    │
    ▼
APPROVED
    ↓
SCHEDULED
    ↓
PUBLISHING          ← Explicit in-flight state (Constitution §14)
    ├──────────► PUBLISH_FAILED
    │
    ▼
PUBLISHED
```

The `PUBLISHING` state is not a design choice in this ADR — it is an inherited architectural invariant from the Engineering Constitution. Its presence makes the in-flight publication zone explicitly visible in the state machine, enabling formal recovery semantics.

Invalid transitions must be rejected by the CAS guard. An attempt to transition directly from `GENERATED` to `PUBLISHED` must fail at the persistence layer.

---

## Concurrency Model

### Article Ingestion Deduplication

- **Mechanism:** Unique database constraint on `(source_id, wp_post_id)`.
- **Behavior:** First INSERT succeeds; concurrent or duplicate INSERTs receive a unique constraint violation, handled gracefully by the application (idempotent success response).
- **Guarantee:** No duplicate `Article` records for the same source post, regardless of concurrent webhook delivery.

### Concurrent State Transitions

- **Mechanism:** CAS conditional UPDATE: `UPDATE ... SET status = 'TARGET' WHERE id = $1 AND status = 'CURRENT'`.
- **Behavior:** If `rows_affected = 0`, the guard rejected the transition (another actor succeeded first). The application must handle this as an explicit conflict, not a silent failure.
- **Guarantee:** Only one actor can successfully perform any given state transition for a given entity instance.

### Publication Exclusive Claim

- **Phase 1 — Scheduler Claim:** `APPROVED → SCHEDULED` via CAS. Only one scheduler can claim a given ContentVersion for publication.
- **Phase 2 — Dispatch Claim:** `SCHEDULED → PUBLISHING` via CAS, within a transaction that also creates a new `PublicationAttempt` record. Only one worker can enter the in-flight state for a given ContentVersion.
- **Recovery:** Any `PUBLISHING` record beyond a defined operational TTL is treated as a potentially orphaned dispatch requiring recovery (see Publication Recovery Protocol).

---

## Publication Recovery Protocol

This protocol is an architectural specification. Implementation parameters (TTL values, retry counts) are operational concerns defined in downstream specifications.

### Phase 1 — Scheduler Claim (Atomic)

```
CAS: APPROVED → SCHEDULED
+ INSERT: content_version_transitions (from=APPROVED, to=SCHEDULED, actor=WORKER)
```

Within one explicit transaction.

### Phase 2 — Dispatch Initiation (Atomic)

```
CAS: SCHEDULED → PUBLISHING
+ INSERT: PublicationAttempt (status=IN_PROGRESS, worker_id, started_at)
+ INSERT: content_version_transitions (from=SCHEDULED, to=PUBLISHING, actor=WORKER)
```

Within one explicit transaction. Once committed, the in-flight state is visible to all processes.

### Phase 3 — External Call (Outside DB Transaction)

The external platform API call occurs here. This operation has no database transaction boundary. The system enters the ambiguous zone (see External Side-Effect Limitation below).

### Phase 4a — Success (Atomic)

```
UPDATE: PublicationAttempt SET status=SUCCESS, external_publication_id='{id}'
+ CAS: PUBLISHING → PUBLISHED
+ INSERT: content_version_transitions (from=PUBLISHING, to=PUBLISHED, actor=WORKER)
```

Within one explicit transaction. Once committed, the publication is definitively recorded.

### Phase 4b — Definitive Failure (Atomic)

```
UPDATE: PublicationAttempt SET status=FAILED, failure_reason='{reason}'
+ CAS: PUBLISHING → PUBLISH_FAILED
+ INSERT: content_version_transitions (from=PUBLISHING, to=PUBLISH_FAILED, actor=WORKER)
```

Within one explicit transaction.

### Phase 4c — Crash Recovery (PUBLISHING Stuck Beyond TTL)

When a recovery process detects `status = PUBLISHING` beyond the defined TTL:

1. Query `publication_attempts` for this `content_version_id` where `external_publication_id IS NOT NULL`.
2. If found: the post was published externally. Execute Phase 4a recovery: update the existing attempt, transition to PUBLISHED.
3. If not found: the outcome is unknown. Create a new `PublicationAttempt`. Transition `PUBLISHING → SCHEDULED` (reset claim). Return to Phase 2.

**This recovery protocol may produce a duplicate post** if the external call succeeded but the `external_publication_id` was never stored. This is the irremovable residual risk formally accepted by the human decision (Decision 2).

### Permanent Failure — Human Intervention Required

`PUBLISH_FAILED` state requires a human editorial decision before any new publication attempt. The system must not automatically retry from `PUBLISH_FAILED`. When recovery attempts exhaust without resolution, the ContentVersion must surface for manual review.

---

## External Side-Effect Limitation (Formal)

This section documents a structural constraint that no persistence strategy can eliminate within the JincSAE's operating environment.

**Fundamental boundary:**

```
PostgreSQL transaction
        ≠
External social platform API call
```

A PostgreSQL `BEGIN ... COMMIT` block provides ACID guarantees over operations within a single database instance. An HTTP call to LinkedIn, Instagram, Facebook, or Bluesky is outside that transaction boundary. Two-phase commit spanning a local database and an external social media API is not achievable. (FACT)

**The irremovable ambiguous zone:**

```
[T1] DB: status = PUBLISHING (committed)
[T2] External API: platform publishes the post (success)
[T3] Network failure / process crash
[T4] DB: external_publication_id = NULL (never updated)
[T5] Recovery: no successful record found → re-dispatch possible
[T6] External API: platform may receive a duplicate POST
```

**Accepted publication semantic (Human Decision 2):**

> The JincSAE persistence architecture guarantees consistency of internal workflow state. For external platform publication, the system implements **at-least-once dispatch with best-effort deduplication**. True exactly-once publication is not achievable without external platform idempotency key support, which is platform-dependent and subject to future verification (see Deferred Decisions). This residual risk is formally accepted and must not be misrepresented as an exactly-once guarantee in any downstream specification or implementation.

**Where provider idempotency keys are available** (to be verified per platform in a future Publication Delivery ADR), they must be used as the primary deduplication mechanism, with `external_publication_id` as secondary verification.

---

## Auditability Model

### Requirement

The system must be able to answer all of the following audit queries:

1. Which article produced this post?
2. Which `ContentVersion` was approved for publication?
3. Who approved it, when, and with what reason?
4. How many publication attempts were made for a given post?
5. Which external post ID was returned by the platform?
6. What was the failure reason for a failed attempt?
7. What states did a given `ContentVersion` pass through, in order?

### Mechanism — Per-Aggregate Audit Tables

Dedicated append-only audit tables per aggregate, with real foreign key constraints, written within the same database transaction as the state change.

**Conceptual structure (not a final schema — schema is a downstream implementation concern):**

```
content_version_transitions:
  id             UUID PRIMARY KEY
  content_version_id  UUID NOT NULL REFERENCES content_versions(id)
  from_state     TEXT NOT NULL
  to_state       TEXT NOT NULL
  actor_id       TEXT NULLABLE          -- NULL for system-automated transitions
  actor_type     TEXT NOT NULL          -- 'HUMAN' | 'SYSTEM' | 'WORKER'
  timestamp      TIMESTAMPTZ NOT NULL
  reason         TEXT NULLABLE
  metadata       JSONB NULLABLE
```

The referential integrity on `content_version_id` ensures that orphaned audit records cannot exist for content versions that have been removed. Entities must use soft-delete to preserve this guarantee.

### Why Not a Single Polymorphic Table

The Architecture Review (ARCH-003) and Red Team (M-003) both identified that a single `state_transitions` table with `entity_type TEXT + entity_id UUID` cannot have database-enforced referential integrity in PostgreSQL. A polymorphic FK approach is acceptable for low-criticality audit trails; it is insufficient for an editorial accountability system where the Engineering Constitution mandates traceability. Per-aggregate tables with real FK constraints are the architecturally correct implementation.

### Actor Model

Three actor types are formally defined for attribution in audit records:

| `actor_type` | Definition | `actor_id` Source |
| :--- | :--- | :--- |
| `HUMAN` | An editorial team member performing a domain action | Resolved by a future Authentication ADR (SDD §14 is PROPOSED - UNDECIDED) |
| `SYSTEM` | An automated pipeline process performing a deterministic transition (e.g., GENERATED → VALIDATED) | A defined system-level constant or component identifier |
| `WORKER` | A background job performing publication dispatch or scheduling | The job or worker process identifier |

The concrete format of `actor_id` for `HUMAN` actors is deferred to the Authentication ADR. The string-typed field accommodates this dependency without schema migration risk.

---

## Consequences

### Positive

- Single PostgreSQL instance serves all persistence and audit needs. No additional infrastructure services for the MVP.
- ACID transactions guarantee consistency across all state-change operations.
- Full audit chain (Article → Brief → ContentVersion → Approval → Publication) is queryable via standard SQL.
- CAS state transitions prevent all identified race conditions without distributed locks.
- Hexagonal Architecture preserved: the domain layer has zero knowledge of PostgreSQL or any ORM.
- Alembic provides structured, reversible schema migrations.
- Event Sourcing remains a documented future evolution path without blocking the MVP.

### Negative

- Schema migrations require discipline (Alembic scripts must be reviewed before production deployment).
- The mandatory transaction boundary (Invariant 1) requires implementation-level enforcement through Repository port design; it cannot be guaranteed by the database schema alone.
- Soft-delete must be adopted across all audited entities, adding a `deleted_at` column and a query filter convention to every aggregate.
- The `PUBLISHING` intermediate state adds one state to every publication path, requiring explicit handling in workers and recovery processes.

### Residual Risks

| Risk | Nature | Mitigation | Residual? |
| :--- | :--- | :--- | :---: |
| Post-crash duplicate publication | Structural; irremovable | PUBLISHING state + recovery protocol + `external_publication_id` guard | ✅ Yes — Formally Accepted |
| Platform without idempotency keys | Platform-dependent | Verify per platform in Publication Delivery ADR | ✅ Yes — Future Mitigation |
| Audit record not written (implementation omission) | Preventable | Mandatory transaction boundary (Invariant 1); Repository review | Managed |
| actor_id format incompatibility after Auth ADR | Low probability | String field; format resolved later without schema breaking change | Low |
| Schema migration error | Standard operational risk | Alembic with `--sql` mode for reviewed migration scripts; staging env | Standard |

---

## Deferred Decisions

The following items are explicitly NOT decided by this ADR and must not be interpreted as locked by it:

| Item | Reason for Deferral | Owner ADR |
| :--- | :--- | :--- |
| Async engine / queue technology | Depends on ADR-002 acceptance (now resolved); separate evaluation | ADR-003 |
| ORM configuration details (SQLAlchemy specifics) | Implementation concern; SQLAlchemy 2.x + asyncpg is the established direction but configuration is downstream | Data Access Specification |
| Audit table schema specifics (column names, indexes) | Follows from aggregate boundary definitions (not yet finalized) | Domain Model Specification |
| `actor_id` concrete format for HUMAN actors | Depends on Authentication ADR | Authentication ADR |
| Publication provider idempotency key support | Requires per-platform empirical research | Publication Delivery ADR |
| Recovery TTL values for PUBLISHING state | Operational parameter | Operations Specification |
| Aggregate boundary formalization | Determines final per-aggregate table names | Domain Model Specification |
| Cloud infrastructure, replication, connection pooling | Infrastructure concerns | Infrastructure ADR |

---

## Downstream ADR Dependencies

| ADR | Dependency on ADR-002 |
| :--- | :--- |
| **ADR-003 — Async Engine / Queue Strategy** | Must know the persistence store to evaluate PostgreSQL-backed queue options (e.g., Procrastinate) as a potential zero-infrastructure-overhead alternative. ADR-002 acceptance unblocks this evaluation. |
| **ADR-004 — ORM & Data Access Detail** | SQLAlchemy 2.x with asyncpg is the established direction from ADR-001 + ADR-002. Formal configuration and patterns are a downstream concern. |
| **ADR-005 — Authentication & Identity** | Provides the concrete format for `actor_id` in `HUMAN`-initiated audit records. |
| **ADR-006 — Publication Delivery Strategy** | Must implement the `PUBLISHING` state and recovery protocol specified in this ADR. Platform idempotency key research outcomes inform this ADR. |
| **ADR-007 — Observability & Audit Query Strategy** | Defines how audit tables are monitored, retained, and exposed for editorial and operational queries. |

---

## Considered and Rejected Approaches Summary

| Approach | Verdict | Primary Reason |
| :--- | :--- | :--- |
| MongoDB (document store) | Rejected | Domain is fundamentally relational; cross-collection transactions add complexity where relational is straightforward |
| Event Sourcing | Rejected for MVP | Genuine benefits (structural audit, native crash recovery) do not justify implementation and operational complexity given current PRD scope; retained as future option |
| Transactional Outbox Pattern | Deferred | Adds infrastructure complexity not justified for MVP; at-least-once + best-effort deduplication is the accepted publication semantic |
| PostgreSQL Pure Relational (no audit table) | Insufficient | Cannot reconstruct state history; violates Engineering Constitution auditability requirement |
| Single polymorphic `state_transitions` table | Not recommended | No real FK enforcement; orphan risk on entity deletion; per-aggregate tables preferred where audit criticality is high |

---

## Related Decisions

- **ADR-001** — Runtime Language & Core Application Stack (Python): Accepted; governs all data access tooling choices.
- **SDD v1.1.0** — Accepted; defines the domain model, hexagonal architecture, and state machine that this ADR implements.
- **Engineering Constitution §14** — Defines the `PUBLISHING` state as part of the mandated state machine.
- **Engineering Constitution §16** — Mandates idempotency for all webhook and job processing.

---

## References

- `docs/ENGINEERING_CONSTITUTION.md` — Foundational constraints; highest authority
- `docs/PRD.md` — Product requirements
- `docs/SDD.md` — Software Design Document v1.1.0
- `docs/adr/ADR-001-Runtime-Language.md` — Runtime decision (Python)
- `docs/adr/ADR-002-Analysis.md` — Persistence analysis artifact
- `docs/adr/ADR-002-ArchReview.md` — Architecture Review (Conditional)
- `docs/adr/ADR-002-RedTeam.md` — Red Team adversarial review
- `docs/adr/ADR-002-Reconciliation.md` — Reconciliation / Final Decision Brief
- `docs/adr/ADR-002-Decision-Readiness.md` — Decision Readiness Review
