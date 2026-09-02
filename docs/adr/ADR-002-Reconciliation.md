---
adr-id: ADR-002
title: "Persistence & Auditability Strategy — Reconciliation / Final Decision Brief"
status: PROPOSED FOR HUMAN DECISION
phase: Reconciliation
related-documents:
  - docs/ENGINEERING_CONSTITUTION.md
  - docs/PRD.md
  - docs/SDD.md
  - docs/adr/ADR-001-Runtime-Language.md
  - docs/adr/ADR-002-Analysis.md
  - docs/adr/ADR-002-ArchReview.md
  - docs/adr/ADR-002-RedTeam.md
---

# ADR-002 Reconciliation / Final Decision Brief

# Persistence & Auditability Strategy

---

## 1. Purpose

This document reconciles three sequential review artifacts:

| Artifact | Role |
| :--- | :--- |
| `ADR-002-Analysis.md` | Original analysis; preliminary recommendation of Option D |
| `ADR-002-ArchReview.md` | Independent Architecture Review; Conditional verdict; 4 Findings |
| `ADR-002-RedTeam.md` | Adversarial Red Team; "Holds With Material Revisions"; 5 required changes |

The reconciliation integrates the adversarial findings with the original analysis, corrects identified gaps, and presents the revised persistence architecture for **human final decision**.

This document does NOT accept ADR-002. It prepares the decision.

No authoritative document has been modified during this reconciliation process.

---

## 2. Decision Context

The JincSAE is a Python-based (ADR-001: Accepted) editorial automation backend. It transforms WordPress-published articles into platform-specific social content through a multi-stage, human-supervised pipeline.

ADR-002 must decide the following, as a unified architectural concern:

1. **Persistence technology** — where and how domain state is stored.
2. **Transactional consistency** — how multi-entity operations are kept atomic.
3. **Concurrency control** — how concurrent actors are safely arbitrated.
4. **Auditability** — how state change history is recorded and queried.
5. **Idempotency** — how duplicate webhook delivery and duplicate job execution are prevented.
6. **External side-effect tracking** — how publication to social platforms is tracked when DB and external API cannot share a transaction.
7. **Failure recovery** — how the system recovers from crashes during publication.

ADR-001 (Python) is accepted and fixed. This ADR does not revisit the runtime.

---

## 3. Authoritative Constraints

The following constraints are grounded in the Engineering Constitution and SDD v1.1.0. They are non-negotiable and inform all decisions in this document.

| Constraint | Source | Persistence Implication |
| :--- | :--- | :--- |
| Article is the canonical factual source | Constitution §4 | All derivative entities must be traceable to a source Article |
| LLM output is untrusted until validated | Constitution §5, SDD §12 | Schema must distinguish raw LLM generation from validated domain state |
| Explicit, traceable state transitions | Constitution §14, SDD §10 | State changes must be persisted atomically with timestamp and actor attribution |
| Human authority is attributable | Constitution §15, SDD §10 | Every approval action must record who approved, when, from which state, to which state |
| Generation and Publication are architecturally separate | Constitution §13, SDD §6 | These must not be collapsed into a single opaque record or transaction |
| Idempotency is mandatory | Constitution §16, SDD §11 | Duplicate webhooks and duplicate job delivery must be handled at the persistence level |
| Regeneration creates a new ContentVersion | SDD §10 | Regeneration is not a state rollback; it is a new entity linked to the same Brief |
| No silent failure | Constitution §15 | Every critical failure must produce an observable state record |
| Hexagonal Architecture | SDD §7, §9 | Persistence layer must be behind Repository ports; domain must not depend on infrastructure |

---

## 4. Source Artifacts

| Artifact | Authority Role | Status |
| :--- | :--- | :--- |
| `docs/ENGINEERING_CONSTITUTION.md` | Foundational policy; highest authority | Active / Accepted |
| `docs/PRD.md` | Product requirements; governs scope | Accepted |
| `docs/SDD.md` | Architecture; v1.1.0 | Accepted |
| `docs/adr/ADR-001-Runtime-Language.md` | Python stack decision | Accepted |
| `docs/adr/ADR-002-Analysis.md` | Persistence analysis; preliminary Option D | Proposed |
| `docs/adr/ADR-002-ArchReview.md` | Independent conditional review | Advisory |
| `docs/adr/ADR-002-RedTeam.md` | Adversarial falsification report | Advisory |

The Engineering Constitution and SDD take precedence over the analysis and reviews in all conflicts.

---

## 5. Original Recommendation

The ADR-002 Analysis proposed **Option D — PostgreSQL as primary state store + a dedicated append-only `state_transitions` table as the audit mechanism**.

This was considered superior over the other evaluated options for the following reasons, as stated in the analysis:

- The domain's entity chain (Article → Brief → ContentVersion → Approval → Publication) is fundamentally relational, mapping naturally to SQL.
- PostgreSQL ACID transactions, unique constraints, and conditional UPDATE provide all required concurrency primitives without distributed infrastructure.
- The `state_transitions` table provides auditable history at minimal operational cost — same database, same migration toolchain.
- Operational simplicity: single PostgreSQL instance, Alembic migrations, SQLAlchemy 2.x ORM.
- Event Sourcing evaluated and rejected: auditability achievable at lower complexity.
- MongoDB evaluated and rejected: relational model superior for cross-entity queries required by the domain.

The preliminary recommendation is directionally sound. The Architecture Review and Red Team identified gaps in protocol specification, not in database selection. This reconciliation refines the protocol without revisiting the database choice.

---

## 6. Architecture Review Reconciliation

### Finding ARCH-001 — CAS Multi-Table Atomicity (Severity: High)

**Original claim:** Conditional UPDATE (`WHERE status = 'X'`) is the primary concurrency safety mechanism.

**Architecture Review critique:** CAS protects single-row updates. It does not guarantee that a subsequent INSERT into `state_transitions` (in a separate call) is atomic with the CAS update. A crash between the two leaves the system with changed state and no audit record — violating the Engineering Constitution's traceability requirement.

**Reconciliation verdict:** ✅ **Critique is valid.** The analysis documented "must be within the same transaction" as a guideline but did not mandate it as an architectural invariant. The reconciled architecture must make this explicit:

> **Invariant (revised):** The atomic unit of a state transition is the pair (CAS UPDATE on current-state table, INSERT into audit history table), executed within a single explicit database transaction. No state transition is considered complete unless both succeed. This must be specified at the Repository Port level.

**Consequence:** The Repository Port interface for state-changing operations must wrap both operations in an explicit transaction context (e.g., SQLAlchemy `async with session.begin()`). This is not a new infrastructure concern; it is an application-layer discipline constraint that must be formalized.

**Evidence classification:** DESIGN DECISION (mandatory).

---

### Finding ARCH-002 — "Effectively Once" Protocol Gap (Severity: High)

**Original claim:** CAS to SCHEDULED + `external_publication_id` guard achieves "effectively once" publication semantics.

**Architecture Review critique:** The recovery protocol is not formally defined. The guard (checking for existing `external_publication_id`) provides no architectural guarantee unless the protocol specifies the exact order: check before dispatch, not after.

**Reconciliation verdict:** ✅ **Critique is valid.** See Section 8 (Fundamental Limitation) and Section 11 (Recovery Semantics) for the corrected protocol.

---

### Finding ARCH-003 — Polymorphic FK Design (Severity: Medium)

**Original claim:** A single `state_transitions` table with `entity_type TEXT + entity_id UUID` provides auditability.

**Architecture Review critique:** PostgreSQL cannot enforce a polymorphic FK. Records become orphans if the referenced entity is deleted. `entity_id` without a real FK is an unconstrained UUID column.

**Reconciliation verdict:** ✅ **Critique is valid.** See Section 12 (Auditability Model) for the corrected design direction.

---

### Finding ARCH-004 — Event Sourcing Rejection Rationale (Severity: Medium)

**Original claim:** "Event Sourcing has zero additional benefit."

**Architecture Review critique:** This claim is factually incorrect. Event Sourcing provides structural audit enforcement and native crash recovery benefits not present in the hybrid model.

**Reconciliation verdict:** ✅ **Critique is valid.** Rejection of Event Sourcing is maintained, but the rationale is corrected. See Section 13 (Event Sourcing Reassessment).

---

## 7. Red Team Reconciliation

### M-001 — Mandatory Transaction Boundary

**Red Team attack:** A state transition without a wrapping transaction leaves the system with changed state and no audit record. "Must be within the same transaction" is aspirational without explicit architectural enforcement.

**Validity:** ✅ Confirmed. The three failure cases documented by the Red Team (state changes without audit, audit written for non-existent state change, crash between two separate DB calls) are all real and non-theoretical.

**Impact:** Architectural invariant upgrade. Not a database selection concern.

**Treatment:** The atomic unit of a state transition MUST be formally defined as (CAS UPDATE + audit INSERT) within one explicit database transaction. This is a new architectural invariant, not a new infrastructure dependency.

**Consequence:** Repository port implementations must use explicit transaction demarcation. Any implementation that performs CAS and audit INSERT in separate connections or separate commits violates the Constitution's traceability principle (Constitution §14).

**Classification:** DESIGN DECISION (mandatory).

---

### M-002 — Publication Semantics + PUBLISHING State

**Red Team attack:** The Red Team demonstrated a concrete failure scenario:

1. Worker calls external platform API.
2. Platform publishes the post and returns success.
3. Network failure prevents the worker from receiving the response.
4. DB remains without `external_publication_id`.
5. Recovery worker finds no successful record and re-dispatches.
6. Platform publishes a duplicate post.

The "effectively once" label collapses. The `external_publication_id` guard cannot fire because the ID was never stored.

**Validity:** ✅ Confirmed. This is an irreducible limitation arising from the impossibility of a two-phase commit spanning the local database and an external social media API (Constitution §8; SDD §15 explicitly acknowledges this class of failure).

**Impact:** The state machine requires a `PUBLISHING` intermediate state. The publication protocol requires formal specification. The semantic label "effectively once" requires honest qualification.

**Treatment:**

- Introduce `PUBLISHING` as an explicit state in the content version lifecycle.
- Define the publication recovery protocol formally (see Section 11).
- Replace "effectively once" with "at-least-once dispatch with best-effort deduplication."
- Acknowledge that deduplication depends on storing `external_publication_id` before any crash; if this fails, duplication is possible and must be treated as a residual risk.

**Note on Engineering Constitution §14 (Explicit State Machines):** The Constitution explicitly lists `PUBLISHING` in its state machine example (Constitution §14). This is not an invented state — it is already contemplated by the Constitution. The original analysis omitted it without documented justification.

**Classification:** DESIGN DECISION (mandatory). FACT: The Constitution already includes PUBLISHING in the example state machine.

---

### M-003 — Polymorphic FK and Referential Integrity

**Red Team attack:** A single `state_transitions` table with `entity_type TEXT + entity_id UUID` has no real FK enforcement. Soft or accidental deletion of audited entities leaves orphan records. Type contamination (wrong entity_type for a given entity_id) is not prevented by the database.

**Validity:** ✅ Confirmed. PostgreSQL cannot enforce multi-table polymorphic FK constraints.

**Impact:** Schema design concern. Does not change persistence strategy direction.

**Treatment — Options evaluated:**

| Design | Referential Integrity | Query Simplicity | Operational Overhead |
| :--- | :---: | :---: | :---: |
| Single polymorphic `state_transitions` | ❌ None | Medium | Low |
| Per-aggregate audit tables with real FK | ✅ Real FK | High | Medium |
| Soft-delete mandate on all entities | ✅ Orphan prevention | Medium | Low |

**Recommended direction:** Move toward per-aggregate audit tables (e.g., `content_version_transitions` with a real FK to `content_versions`) where referential integrity matters most. The polymorphic table may be retained for lower-criticality entities where the trade-off is acceptable, but the design must acknowledge the FK limitation explicitly and mandate a soft-delete or append-only strategy on all audited entities.

**Classification:** DESIGN DECISION (conditional). Exact schema is a downstream implementation concern; the principle (no unconstrained polymorphic FKs on critical audit paths) is architectural.

---

### M-004 — Actor Model

**Red Team attack:** The `state_transitions` schema defines `actor_id TEXT` without distinguishing system-automated transitions from human-initiated ones. SDD §14 (Authentication Boundary) is explicitly `PROPOSED - UNDECIDED`. There is no defined `actor_id` source for system-initiated transitions.

**Validity:** ✅ Confirmed. Unresolved actor model creates two concrete problems: (1) NULL vs non-NULL actor_id is not schema-enforced, (2) system actors (background workers, validators) have no defined identity representation.

**Treatment:** Define the actor model concept at the architecture level:

| Actor Type | Definition | actor_id Source |
| :--- | :--- | :--- |
| `HUMAN` | Editorial team member performing a review/approval action | Identity token resolved by Authentication ADR (future) |
| `SYSTEM` | Automated process performing a deterministic transition (e.g., GENERATED → VALIDATED) | Constant system identifier (e.g., `"system"` or a well-known UUID) |
| `WORKER` | Background job performing publication dispatch or scheduling | Worker process identifier or job ID |

The specific `actor_id` format for `HUMAN` actors depends on the Authentication ADR (not yet decided). The schema must accommodate this dependency by using a string identifier that can be resolved once the Authentication ADR is accepted.

**Note:** This does not block the persistence decision. The actor model concept is sufficient for ADR-002; the concrete format is deferred to the Authentication ADR.

**Classification:** DESIGN DECISION (concept locked); OPEN QUESTION (concrete format, Authentication ADR dependency).

---

### M-005 — Event Sourcing Rejection Rationale

**Red Team finding:** The claim "zero additional benefit" is factually incorrect. Event Sourcing provides real structural benefits: (1) audit enforcement by architecture (not by discipline), (2) native crash recovery, (3) causal chain queryability.

**Validity:** ✅ Confirmed.

**Treatment:** The rejection rationale is corrected. See Section 13 (Event Sourcing Reassessment) for the full balanced assessment.

**Classification:** FACT (the benefits exist). DESIGN DECISION (rejected for MVP despite benefits).

---

## 8. Fundamental Limitation: External Side Effects

This section documents a structural constraint that no persistence strategy can eliminate.

### The Boundary Problem

A PostgreSQL transaction provides ACID guarantees over operations within a single database instance. A call to LinkedIn, Instagram, Facebook, or Bluesky API is outside that transaction boundary. There is no protocol available for a two-phase commit spanning a local database and an external social media API. (FACT)

Therefore:

```
DB transaction commit
          ≠
External API call success
```

These two events are independent. Any failure between them creates a state of **observable ambiguity**:

```
SCENARIO: Post-External-Success Crash

[T1] Worker CAS: APPROVED → SCHEDULED (DB committed)
[T2] Worker CAS: SCHEDULED → PUBLISHING (DB committed)
[T3] Worker calls LinkedIn POST /shares
[T4] LinkedIn accepts and publishes (external success)
[T5] Network failure: worker does not receive HTTP 200
[T6] Worker process crashes or times out
                        ↑
            AMBIGUOUS ZONE: Was the post published?

[T7] DB state: status = PUBLISHING, external_publication_id = NULL
[T8] Recovery worker: no external_publication_id found → re-dispatches
[T9] LinkedIn publishes a second post
```

### What Is Actually Achievable

| Guarantee | Achievable? | Condition |
| :--- | :---: | :--- |
| Exactly Once to external platform | ❌ No | Requires 2PC spanning DB + external API — impossible |
| At Least Once | ✅ Yes | With retries; the platform may receive multiple calls |
| At Most Once | ✅ Yes | Without retries; accepts potential loss |
| Effectively Once | ✅ Conditionally | At-least-once + deduplication via `external_publication_id` — only when the ID is successfully stored |
| Best-Effort Deduplication | ✅ Yes | The practical maximum for platforms without idempotency keys |

### Platform Idempotency Key Status

The availability of platform-level idempotency keys would significantly reduce the ambiguous zone. However, this requires platform-specific research:

| Platform | Idempotency Key for Post Creation | Notes |
| :--- | :--- | :--- |
| LinkedIn | Unknown — requires verification | Some API endpoints support idempotency tokens |
| Instagram Graph API | Unknown — requires verification | Not documented for post creation |
| Facebook Graph API | Unknown — requires verification | Not documented for post creation |
| Bluesky AT Protocol | Unknown — requires verification | Not documented for post creation |

**If any platform supports idempotency keys**, these should be used as the primary deduplication mechanism, with `external_publication_id` as secondary verification. (OPEN QUESTION — blocks implementation, not architecture direction)

### Honest Semantic Label

The label **"effectively once"** is retained only under the following qualified definition:

> **"At-least-once dispatch with best-effort deduplication. Deduplication is achievable when `external_publication_id` is successfully stored in the database before the next retry window. When the external API call succeeds but the response is lost before the ID is stored, the system cannot prevent a duplicate dispatch. This residual risk is accepted as a fundamental boundary limitation, not a design failure."**

This definition must appear in the accepted ADR. It must not be softened to "effectively once" without the qualification.

---

## 9. Corrected Persistence Model

After reconciliation, the corrected architectural model is:

### Database

- **PostgreSQL** as the single persistence store.
- No secondary database for the MVP.
- Rationale: Relational entity chain (Article → Brief → ContentVersion → Approval → Publication) maps naturally to SQL. ACID transactions, unique constraints, and conditional UPDATE provide all required concurrency primitives. (FACT + DESIGN DECISION)

### Explicit Transaction Boundary (M-001 Correction)

Every state transition is defined as an atomic unit consisting of:

1. A conditional UPDATE (CAS) on the current-state table.
2. An INSERT into the audit history table (per-aggregate, see below).

Both must execute within a single explicit database transaction. Repository port implementations must enforce this at the Use Case boundary. Application code that separates these two operations into different DB calls or different commits violates this invariant.

### Current-State Tables

Mutable tables holding the current domain state. Key tables (not a final schema — schema is an implementation concern):

- `articles` — ingest record, canonical source reference
- `editorial_briefs` — linked to article
- `content_versions` — linked to brief; append-only versioning; current version is highest `version_number` per (brief_id, platform)
- `publication_attempts` — linked to content_version; append-only; status + `external_publication_id` field

### Per-Aggregate Audit Tables (M-003 Correction)

Replace the single polymorphic `state_transitions` table with per-aggregate audit tables where referential integrity matters:

- `content_version_transitions` — real FK to `content_versions(id)`
  - Fields: `id`, `content_version_id (FK)`, `from_state`, `to_state`, `actor_id`, `actor_type ENUM(HUMAN, SYSTEM, WORKER)`, `timestamp`, `reason (nullable)`, `metadata JSONB (nullable)`
- `publication_attempt_transitions` — real FK to `publication_attempts(id)` (if needed for attempt-level audit)

Entities must use soft-delete (`deleted_at TIMESTAMPTZ`) rather than hard-delete to prevent audit record orphaning.

### State Machine (Constitution §14 Restored)

The Engineering Constitution §14 explicitly includes `PUBLISHING` in the state machine example. The original analysis omitted this state without documented justification. The corrected state machine is:

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
PUBLISHING          ← Explicit intermediate state (M-002)
    ├──────────► PUBLISH_FAILED
    │
    ▼
PUBLISHED
```

`PUBLISHING` makes the in-flight ambiguous zone visible in the state machine rather than leaving it implicit.

### Actor Model (M-004)

Three actor types are defined:

| `actor_type` | Meaning | `actor_id` Source |
| :--- | :--- | :--- |
| `HUMAN` | Editorial user performing a domain action | Resolved by Authentication ADR |
| `SYSTEM` | Automated pipeline process (validator, scheduler) | Well-known constant per system component |
| `WORKER` | Background job executing publication dispatch | Job ID or worker process identifier |

### Idempotency

- **Ingestion:** Unique constraint on `(source_id, wp_post_id)` prevents duplicate Article records. Application handles constraint violation gracefully (returns success; article exists).
- **Publication:** CAS `APPROVED → SCHEDULED` as exclusive claim; CAS `SCHEDULED → PUBLISHING` as in-flight lock; `external_publication_id` as deduplication anchor for post-crash recovery (best-effort).

### Data Access

- SQLAlchemy 2.x (async) with `asyncpg` driver. (DESIGN DECISION — consistent with ADR-001 Python stack)
- Alembic for schema migrations.
- Repository pattern: per-aggregate concrete port interfaces defined in the Application layer; SQLAlchemy adapters in the Infrastructure layer.
- SQLModel is not recommended — it risks collapsing domain and persistence models. (ARCHITECTURAL JUDGMENT)

---

## 10. Concurrency Model

### Duplicate Webhook (Scenario S1)

Two identical WordPress webhooks arrive simultaneously.

- **Mechanism:** Unique constraint on `(source_id, wp_post_id)`. First INSERT succeeds; second receives a constraint violation.
- **Application handling:** Catch constraint violation; return success (idempotent). No data corruption possible.
- **Verdict:** ✅ PASS — no changes required from reconciliation.

### Concurrent Approval (Scenario S2)

Two editorial users attempt to approve the same ContentVersion simultaneously.

- **Mechanism:** CAS `UPDATE content_versions SET status = 'APPROVED' WHERE id = $1 AND status = 'PENDING_REVIEW'`, wrapped in an explicit transaction with the audit INSERT.
- **Application handling:** If `rows_affected = 0`, a conflict occurred; the second user receives a conflict error.
- **M-001 correction:** Both the CAS UPDATE and the `content_version_transitions` INSERT must be in the same transaction.
- **Verdict:** ✅ PASS after M-001 correction.

### Regeneration Race (Scenario S3)

An editor requests regeneration while another approves the same ContentVersion.

- **Gap identified:** The state machine does not currently define whether regeneration is permitted from `PENDING_REVIEW`. If permitted, CAS for approval may succeed just before the regeneration request, leaving the system with an approved ContentVersion and an orphaned regeneration request.
- **Treatment:** This is a domain modeling decision, not a persistence decision. The Domain Specification must define whether `PENDING_REVIEW → [regeneration request]` is a permitted transition. Until defined, the safe default is: regeneration is only permitted from states where no approval is pending.
- **Verdict:** ⚠️ PARTIAL — requires Domain Specification resolution. Persistence mechanism is capable; the state machine boundary is not yet defined.

### Concurrent Publication Workers (Scenario S5)

Multiple background workers attempt to publish the same ContentVersion.

- **Mechanism:** CAS `SCHEDULED → PUBLISHING` is the exclusive claim. Only one worker succeeds; others find `status ≠ SCHEDULED` and exit without action.
- **Verdict:** ✅ PASS — CAS acts as an atomic lock for the in-flight publication claim.

### Retry Storm (Scenario S8)

Multiple retries are dispatched after a transient failure.

- **Mechanism:** CAS guards prevent re-entry into `PUBLISHING` if already in that state. Each retry must go through the full state check.
- **Verdict:** ✅ PASS.

---

## 11. Recovery Semantics

### Formal Recovery Protocol for PUBLISHING State

The following protocol defines the lifecycle of a publication dispatch and its recovery:

**Phase 1 — Claim (atomic):**

```
CAS: APPROVED → SCHEDULED
```

Atomic. If conflict, exit. Creates a stable claim owned by no specific worker yet.

**Phase 2 — Dispatch Initiation (atomic):**

```
CAS: SCHEDULED → PUBLISHING
INSERT: PublicationAttempt (status = IN_PROGRESS, worker_id = ?, timestamp = now)
```

Both within one explicit transaction. This makes the in-flight state visible.

**Phase 3 — External Call (non-atomic, outside DB transaction):**

```
HTTP POST → External platform
```

This operation has no DB transaction. The system is in the ambiguous zone.

**Phase 4a — Success (atomic):**

```
UPDATE: PublicationAttempt SET status = SUCCESS, external_publication_id = '{id}'
CAS: PUBLISHING → PUBLISHED
INSERT: content_version_transitions (from=PUBLISHING, to=PUBLISHED, actor=WORKER)
```

All within one explicit transaction. Once committed, the post is definitively published.

**Phase 4b — Definitive Failure (atomic):**

```
UPDATE: PublicationAttempt SET status = FAILED, failure_reason = '{reason}'
CAS: PUBLISHING → PUBLISH_FAILED
INSERT: content_version_transitions (from=PUBLISHING, to=PUBLISH_FAILED, actor=WORKER)
```

All within one explicit transaction. Marks the failure definitively.

**Phase 4c — Ambiguous / Crash Recovery:**

When a worker detects `status = PUBLISHING` beyond a defined TTL (e.g., 5 minutes — an implementation parameter):

1. Query `publication_attempts` for this `content_version_id` where `status = SUCCESS` OR `external_publication_id IS NOT NULL`.
2. If found → the post was published. Execute Phase 4a recovery: update the existing attempt, transition to PUBLISHED.
3. If not found → the outcome is unknown. **Create a new PublicationAttempt. Return to Phase 2.** (This may produce a duplicate post — see Section 8 residual risk.)

**Distinguishing Retry Types** (SDD §15):

| Type | Trigger | DB Record | Human Involvement |
| :--- | :--- | :--- | :--- |
| Technical Retry | Transient failure (network, 503) | New `PublicationAttempt` row | No |
| Post-Crash Recovery | PUBLISHING stuck beyond TTL | New `PublicationAttempt` row | No (unless ambiguity) |
| Human-Authorized Retry | Permanent failure; editorial decision | New `PublicationAttempt` + state reset to APPROVED | Yes — required |
| Editorial Regeneration | Quality rejection | New `ContentVersion` | Yes — required |

**When Human Intervention Is Required:**

- `PUBLISH_FAILED` state requires a human editorial decision before any new attempt. The system must not automatically retry from `PUBLISH_FAILED`.
- When ambiguity from a crash-recovery scenario is flagged and no `external_publication_id` is found after N attempts, the system should surface the case for manual resolution rather than continuing to retry indefinitely.

**Residual Risk (Irremovable):**

> When a publication call succeeds externally but the response is lost before `external_publication_id` is stored, the recovery protocol cannot distinguish success from unknown failure. A duplicate post may be dispatched. This risk cannot be eliminated without external API idempotency key support. It is accepted as a fundamental external-boundary limitation.

---

## 12. Auditability Model

### State Transition History (Per-Aggregate Tables)

**Approach:** Per-aggregate audit tables with real FK constraints, inserted within the same transaction as the state change.

**Benefits:**

- Referential integrity enforced at DB level. (FACT)
- Natural SQL queries: `SELECT * FROM content_version_transitions WHERE content_version_id = $1 ORDER BY timestamp`.
- State change history is never orphaned if the entity uses soft-delete.
- Inserted within the same transaction as the CAS — no audit divergence possible.

**Costs:**

- One additional table per audited aggregate.
- Schema migration required when new auditable entities are added.
- Application discipline required: Repository port must always include the audit INSERT.

**Queryability:** All audit questions from ADR-002-Analysis §4.F are answerable:

- "Which article produced this post?" → FK chain from `content_versions` → `editorial_briefs` → `articles`.
- "Which ContentVersion was approved?" → `content_version_transitions WHERE to_state = 'APPROVED'`.
- "Who approved it, when, with what reason?" → `actor_id`, `actor_type`, `timestamp`, `reason` columns.
- "How many publication attempts?" → `SELECT COUNT(*) FROM publication_attempts WHERE content_version_id = $1`.
- "Which external post ID?" → `publication_attempts.external_publication_id`.
- "What was the failure reason?" → `publication_attempts.failure_reason`.

**Comparison with Event Sourcing:**

| Dimension | Per-Aggregate Audit Tables | Event Sourcing |
| :--- | :--- | :--- |
| Audit enforcement | By application discipline (transaction scope) | By architecture (events are the only state source) |
| Crash recovery | Best-effort with recovery protocol | Native (event replay) |
| Query simplicity | Direct SQL on audit tables | Requires read projections |
| Current-state query | Direct table read | Requires projection rebuild |
| Schema evolution | Alembic migrations | Event versioning + upcasting |
| Debugging | SELECT queries | Event replay tooling |
| MVP complexity | Low | High |

**Conclusion:** Per-aggregate audit tables satisfy the Engineering Constitution's auditability requirement at MVP-appropriate complexity. Event Sourcing's structural enforcement advantage is real but achievable at lower cost through the mandatory transaction boundary invariant (M-001).

---

## 13. Event Sourcing Reassessment

### Genuine Benefits (Not "Zero")

Event Sourcing provides real benefits for this domain:

1. **Structural audit enforcement:** In an event-sourced system, state IS derived from events. There is no code path that changes state without creating an event. The "audit table neglect" risk (identified in ARCH-003) does not exist.

2. **Native crash recovery:** If the event `PublicationDispatched` is stored before the external call, recovery is semantically clear: the event exists, therefore the attempt was made. The ambiguous zone (Section 8) is reduced.

3. **Causal chain queryability:** Events carry `causation_id` linking each event to its cause. The full "why was this published?" chain is natively queryable.

### Costs and Complexity

1. **Projections required:** Current-state queries require read projections rebuilt from events. Without dedicated projection infrastructure, this adds read complexity.

2. **Event schema evolution:** Stored events are immutable. Schema changes require event versioning strategies (upcasting, versioned events) from day one.

3. **Operational debugging:** State reconstruction requires event replay tooling, not a simple SELECT.

4. **PRD does not evidence temporal query requirements.** The audit questions in ADR-002-Analysis §4.F are all point-in-time queries answerable by audit tables. No PRD requirement evidences the need to reconstruct state at an arbitrary past timestamp. (FACT — PRD examined, no such requirement found)

5. **Team learning curve:** Event Sourcing is non-trivial to implement correctly in Python. The pattern requires careful design from day one and does not easily tolerate implementation mistakes.

### Honest Assessment of Structural Benefits vs. Reconciled Alternatives

The structural audit enforcement advantage of Event Sourcing is addressed by the M-001 correction (mandatory transaction boundary). When the CAS + audit INSERT are guaranteed to be in the same transaction, audit divergence becomes impossible by application invariant — equivalent to Event Sourcing's structural guarantee at a fraction of the complexity.

The native crash recovery advantage is partially addressed by the `PUBLISHING` state and formal recovery protocol (M-002). The residual risk (ambiguous zone) remains, but this exists in Event Sourcing as well unless the event is stored before the external call — which is a design choice, not an inherent ES advantage.

### Verdict

**Event Sourcing: REJECTED FOR MVP / RETAIN AS FUTURE OPTION.**

Rejection rationale (corrected): Event Sourcing provides genuine structural benefits in audit enforcement and crash recovery. These benefits do not justify MVP implementation complexity because: (a) the audit enforcement benefit is achievable through mandatory transaction boundary discipline; (b) the crash recovery benefit is partially addressed by the PUBLISHING state and recovery protocol; (c) no PRD requirement evidences the need for temporal state reconstruction or event replay; (d) projection infrastructure, event schema versioning, and operational tooling add complexity disproportionate to the current scope.

Event Sourcing should be retained as a future evolution option if: (a) compliance requirements mandate full event replay, (b) temporal state queries become a product requirement, or (c) audit divergence is observed in production despite the transaction boundary invariant.

---

## 14. Corrected Decision Matrix

Weights are assigned based on Engineering Constitution priority and PRD scope. No driver is duplicated.

| Driver | Weight | Option A: PostgreSQL | Option B: MongoDB | Option C: Event Sourcing | Option D: PostgreSQL + Hybrid Audit (Corrected) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Transactional Integrity | Critical | ✅ 5 | ⚠️ 3 | ⚠️ 3 | ✅ 5 |
| Auditability (with transaction invariant) | Critical | ⚠️ 3 | ⚠️ 2 | ✅ 5 | ✅ 5 |
| Concurrency Control | Critical | ✅ 5 | ⚠️ 3 | ✅ 4 | ✅ 5 |
| Failure Recovery (incl. PUBLISHING) | High | ⚠️ 3 | ⚠️ 2 | ✅ 4 | ⚠️ 4* |
| External Side-effect Tracking | High | ⚠️ 3 | ⚠️ 2 | ⚠️ 3 | ⚠️ 4* |
| Operational Complexity | High | ✅ 5 | ✅ 4 | 🔴 2 | ✅ 5 |
| Queryability | High | ✅ 5 | ⚠️ 3 | ⚠️ 3** | ✅ 5 |
| Implementation Complexity | High | ✅ 5 | ✅ 4 | 🔴 2 | ✅ 5 |
| Evolution / Reversibility | Medium | ✅ 4 | ⚠️ 3 | 🔴 2 | ✅ 4 |
| Migration Support | Medium | ✅ 5 | ⚠️ 3 | ⚠️ 3 | ✅ 5 |

*Option D scores 4 (not 5) on Failure Recovery and External Side-effect Tracking because the residual risk of post-crash external ambiguity is irreducible. No option achieves 5 on External Side-effect Tracking for the same reason.
**Event Sourcing queryability requires projection infrastructure; current-state queries are not direct.

**Option D scores highest** across the combined weight of Critical and High drivers after the M-001/M-002 corrections. The corrections do not change the database selection; they formalize the protocol.

---

## 15. Residual Risks

The following risks remain after all reconciliation corrections:

| Risk | Severity | Mitigation | Residual? |
| :--- | :---: | :--- | :---: |
| External API success + response lost before DB write | High | PUBLISHING state; recovery protocol; external_publication_id guard | ✅ Yes — irremovable |
| Platform does not support idempotency keys | Medium | Best-effort deduplication only | ✅ Yes — platform-dependent |
| Audit INSERT skipped outside transaction scope | Medium | Mandatory transaction boundary invariant (M-001) | Reduced to implementation discipline |
| ContentVersion orphaned by hard-delete | Low | Soft-delete mandate | Manageable |
| actor_id format incompatibility after Auth ADR | Low | String field; format resolved later | Low |
| Schema migration errors during evolution | Medium | Alembic with reviewed migration scripts; staging env | Standard practice |
| Regeneration race (PENDING_REVIEW + regen request) | Low | Domain Specification must define permitted transitions | Deferred — not a persistence gap |
| Recovery worker TTL misconfiguration | Medium | TTL must be explicitly configured and monitored | Implementation concern |

---

## 16. Decision Sensitivity

The following conditions would change the architectural recommendation:

**IF** compliance or regulatory requirements mandate complete event replay and point-in-time state reconstruction:
**THEN** Event Sourcing becomes architecturally justified. The current analysis does not evidence this requirement in the PRD.

**IF** external platforms (LinkedIn, Instagram, Facebook, Bluesky) expose idempotency keys for post creation:
**THEN** the "effectively once" label becomes more accurate and the residual duplicate-post risk is materially reduced.

**IF** the system must support multiple concurrent editorial teams with high-contention approval workflows:
**THEN** pessimistic locking (`SELECT FOR UPDATE`) should be reconsidered over CAS for approval transitions. The current PRD does not evidence high-contention scenarios.

**IF** the domain grows to include multi-tenant deployments at the MVP stage:
**THEN** the `(source_id, wp_post_id)` deduplication strategy requires schema redesign. Current MVP assumption is single-newsroom deployment.

**IF** the team cannot enforce mandatory transaction boundary discipline through code review and architecture tests:
**THEN** Event Sourcing's structural enforcement advantage becomes a stronger argument. The M-001 mitigation depends on implementation discipline.

---

## 17. Human Decision Options

### OPTION A — Accept PostgreSQL + Hybrid Audit with M-001 and M-002 Mandatory Corrections

**Description:** Accept the corrected Option D: PostgreSQL + per-aggregate audit tables + PUBLISHING state + formal recovery protocol + explicit transaction boundary invariant.

**Benefits:** Highest decision matrix score; operational simplicity; full relational integrity; no new infrastructure; satisfies all Constitution constraints; clear implementation path.

**Costs:** Requires two mandatory architectural corrections to be reflected in the final ADR before acceptance. Residual external-side-effect risk accepted.

**Risks:** Residual duplicate-post risk if platform lacks idempotency keys. Actor model formally depends on Authentication ADR.

**Architectural consequences:** Locks in PostgreSQL as the sole persistence technology for the MVP. Locks in per-aggregate audit tables. Locks in PUBLISHING state and recovery protocol.

---

### OPTION B — Accept PostgreSQL Pure Relational (Simpler Audit)

**Description:** Accept PostgreSQL as the persistence store without the dedicated state transition history table. Audit only via `created_at`, `updated_at`, `actor_id` columns on critical tables.

**Benefits:** Simpler schema; fewer tables; lower implementation overhead.

**Costs:** Cannot answer "what states did this ContentVersion pass through?" without fragile timestamp analysis. Violates Engineering Constitution §14 (Explicit State Transitions) and SDD §20 (auditability requirement).

**Risks:** Insufficient for editorial accountability requirements. Likely to require schema upgrade within the MVP delivery cycle.

**Verdict:** Not recommended. It does not satisfy the Constitution's auditability requirement without the audit history table. This option would require documented acceptance of a Constitution violation.

---

### OPTION C — Adopt Event Sourcing

**Description:** Replace all current-state tables and audit tables with an event store. Derive current state from event projections.

**Benefits:** Structural audit enforcement; native crash recovery; full temporal queryability.

**Costs:** Significant implementation complexity; projection infrastructure; event schema versioning; operational tooling; high team learning curve.

**Risks:** Disproportionate to MVP scope. No PRD requirement evidences need for Event Sourcing.

**Verdict:** Not recommended for the MVP. Valid future evolution option.

---

### OPTION D — Defer Decision Pending Missing Evidence

**Description:** Pause ADR-002 until platform idempotency key support is verified and/or the Authentication ADR is resolved.

**When to choose:** If the human decision-maker judges that the residual external-side-effect risk is unacceptable without confirmed platform idempotency key support.

**Costs:** Delays downstream ADRs (queue strategy, ORM/data access, publication delivery).

**Verdict:** Acceptable only if the residual risk (Section 15, first row) is considered blocking.

---

## 18. Recommended Decision

The reconciliation analysis supports the following technical recommendation:

> **OPTION A — PostgreSQL + Hybrid Audit (Corrected) with mandatory M-001 and M-002 protocol specifications incorporated into the final ADR.**

This recommendation is grounded in:

1. Highest decision matrix score across Critical and High priority drivers (SUPPORTED INFERENCE from matrix).
2. Full alignment with Engineering Constitution constraints (FACT).
3. Consistency with SDD §17 (PostgreSQL as strong candidate) and SDD §14 (explicit state machines including PUBLISHING) (FACT).
4. Resolution of all identified architectural gaps without introducing unjustified infrastructure complexity (DESIGN DECISION).
5. Honest qualification of external side-effect limitations without false guarantees (FACT).

This recommendation becomes architectural guidance only after human decision. It is not self-executing.

**The following must be explicitly incorporated into the accepted ADR — not as guidelines but as binding architectural invariants:**

1. Mandatory transaction boundary: CAS + audit INSERT in one explicit DB transaction.
2. PUBLISHING intermediate state in the content version lifecycle.
3. Formal recovery protocol as specified in Section 11.
4. "At-least-once with best-effort deduplication" as the honest publication semantic label.
5. Per-aggregate audit tables with real FK constraints (or soft-delete mandate for polymorphic design).
6. Actor model with `actor_type ENUM(HUMAN, SYSTEM, WORKER)`.

---

## 19. Decision Required

**HUMAN DECISION REQUIRED.**

The following elements require explicit human acceptance or rejection:

| # | Decision Point | Implication |
| :--- | :--- | :--- |
| 1 | **Persistence strategy** — PostgreSQL + Hybrid Audit (Corrected) vs. alternative | Locks primary storage for the MVP |
| 2 | **Audit model** — Per-aggregate tables with real FK vs. polymorphic single table | Locks audit schema design direction |
| 3 | **Recovery semantics** — PUBLISHING state + formal recovery protocol accepted | Locks state machine and worker protocol |
| 4 | **Residual external side-effect risk accepted** — duplicate post risk acknowledged as irremovable | Allows design to proceed without platform idempotency key resolution |
| 5 | **Event Sourcing status** — REJECTED FOR MVP / RETAIN AS FUTURE OPTION | Closes the Event Sourcing evaluation for the current scope |

No implementation should begin before the human decision on items 1–5 is recorded.

---

## 20. Consequences of Acceptance

If Option A is accepted, the following architectural elements are **LOCKED**:

- PostgreSQL is the persistence technology for the JincSAE MVP.
- No secondary database is introduced.
- State transitions require explicit transaction demarcation (CAS + audit INSERT in one transaction).
- The content version lifecycle includes `PUBLISHING` as an explicit intermediate state.
- The publication recovery protocol is as specified in Section 11.
- Publication semantics are labeled "at-least-once with best-effort deduplication."
- Per-aggregate audit tables with real FK constraints (or soft-delete mandate) are the auditability mechanism.
- SQLAlchemy 2.x (async) with asyncpg is the data access library.
- Alembic is the migration tool.
- Repository pattern (per-aggregate port interfaces) is mandatory.
- Event Sourcing is closed for the MVP scope.

---

## 21. Consequences of Rejection

If the recommendation is rejected:

- **If rejected in favor of MongoDB:** The relational chain analysis must be revisited. Cross-collection transaction complexity for multi-entity workflows must be formally addressed. Traceability requirements may be harder to satisfy.
- **If rejected in favor of Event Sourcing:** Full event sourcing infrastructure must be designed: event store schema, projection strategy, event versioning policy, read model synchronization, operational tooling.
- **If rejected and decision deferred:** All downstream ADRs (queue strategy, ORM, publication delivery) are blocked until persistence is resolved.

---

## 22. Downstream ADR Dependencies

The following ADRs depend on the ADR-002 outcome and must not be defined until ADR-002 is accepted:

| ADR | Dependency on ADR-002 |
| :--- | :--- |
| **ADR-003 — Async Engine / Queue Strategy** | Must know the persistence store to evaluate Postgres-backed queues (Procrastinate) vs. external queues. If PostgreSQL is accepted, a Postgres-backed queue is a viable option that avoids additional infrastructure. |
| **ADR-004 — ORM & Data Access Strategy** | Depends on PostgreSQL acceptance. SQLAlchemy 2.x is already indicated; formal decision locks the ORM adapter layer. |
| **ADR-005 — Authentication & Identity (future)** | Provides the `actor_id` format for `HUMAN` actors in audit records. |
| **ADR-006 — Publication Delivery Strategy (future)** | Must implement the PUBLISHING state and recovery protocol specified in this ADR. Platform idempotency key research outcome will inform this ADR. |
| **ADR-007 — Observability & Audit Strategy (future)** | Must define how audit tables are monitored, retained, and exposed for editorial queries. |

---

## 23. Final Status

```
status: PROPOSED FOR HUMAN DECISION
```

This document is a reconciliation brief. It is not an accepted decision.

The ADR-002 decision becomes ACCEPTED only after the human decision-maker explicitly approves one of the options in Section 17 and the final `ADR-002.md` is authored to reflect that decision, incorporating the mandatory corrections from this reconciliation.
