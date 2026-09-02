# ADR-002 Red Team Report — Adversarial Review

**Status:** Adversarial Review Artifact  
**Target:** `docs/adr/ADR-002-Analysis.md` + `docs/adr/ADR-002-ArchReview.md`  
**Authority Hierarchy Respected:** Constitution > PRD > SDD > ADR-001 > ADR-002-Analysis  
**Date:** 2026-08-31  

> **Red Team Posture:** This report assumes the recommendation is wrong until proven otherwise.  
> Do not read this report as a confirmation of any prior analysis.

---

## 1. Executive Verdict

**🟠 RECOMMENDATION HOLDS WITH MATERIAL REVISIONS**

The preliminary recommendation (Option D: PostgreSQL + State Transition History) survives the Red Team attack on the *database choice* and the *audit strategy*. However, **two of the four primary findings represent genuine architectural gaps** that, if left unresolved, transform the "effectively once" and "multi-table atomicity" claims into implementation-level promises with no architectural enforcement. These gaps do not invalidate the choice of PostgreSQL—but they do invalidate the *protocol* as currently specified.

The database is not the problem. The protocol is underspecified.

---

## 2. Threat Model

The Red Team evaluates the design against the following failure classes:

| Threat Class | Description |
| :--- | :--- |
| **T1 — Application Crash Mid-Transaction** | Process dies between DB write and external call, or between two DB writes |
| **T2 — Concurrent State Mutation** | Two actors attempt to modify the same entity simultaneously |
| **T3 — Audit Divergence** | State changes without audit trail, or audit trail written for non-existent state changes |
| **T4 — External API Non-Determinism** | External call succeeds but application cannot confirm it (timeout, network failure) |
| **T5 — Retry Stacking** | Multiple retry workers claim the same job and dispatch it concurrently |
| **T6 — Phantom State** | Entity appears in one state in the DB but a different state in business reality |
| **T7 — Historical Reconstruction Failure** | After 6 months, an audit query returns incomplete or misleading results |

---

## 3. Claims Under Attack

### Claim 1 — "CAS is sufficient for concurrency safety"

| Field | Content |
| :--- | :--- |
| **CLAIM** | Conditional UPDATE (`WHERE status = 'X'`) is the primary and sufficient concurrency mechanism |
| **STATUS** | Under attack |
| **ATTACK** | CAS on a single row is atomic. A workflow transition involving multiple tables is NOT automatically atomic unless wrapped in an explicit database transaction. The analysis does not specify where transactions begin and end. |
| **EVIDENCE** | PostgreSQL `UPDATE ... WHERE status = 'X'` is a single atomic statement. However, if the application then issues a separate `INSERT INTO state_transitions` outside a wrapping transaction, a crash between them leaves the system with changed state and no audit record. (FACT) |
| **COUNTEREXAMPLE** | `conn.execute(update_status_sql); [crash here]; conn.execute(insert_audit_sql)` — state changed, audit record lost. This is not a theoretical failure; it is the default behavior in async Python if the developer does not explicitly scope a transaction. |
| **VERDICT** | ⚠️ PARTIAL SURVIVAL — CAS protects single-row concurrency. It does NOT protect multi-statement atomicity. The claim is directionally valid only if an explicit Unit of Work / transaction scope is mandated in the architecture. |

---

### Claim 2 — "effectively once publication semantics are achievable"

| Field | Content |
| :--- | :--- |
| **CLAIM** | The combination of SCHEDULED state + external_publication_id check achieves "effectively once" semantics |
| **STATUS** | Under attack |
| **ATTACK** | "Effectively once" is not a formally defined distributed systems guarantee. The analysis defines it as "at-least-once with duplicate detection using external platform IDs." This is only correct if: (a) the guard query always runs before a retry, (b) the external platform returns a stable, unique post ID, and (c) that ID is successfully stored before the next retry window. None of these three conditions are guaranteed in the protocol as described. |
| **EVIDENCE** | See Section 5 for full protocol falsification. |
| **COUNTEREXAMPLE** | Worker publishes to LinkedIn (success). LinkedIn returns `post_id = abc123`. Worker receives response. Worker crashes before `UPDATE publication_attempts SET external_publication_id = 'abc123'`. Recovery worker finds `status = SCHEDULED`, no external_publication_id, and re-dispatches. **LinkedIn receives a duplicate POST.** The guard never fires because the ID was never stored. |
| **VERDICT** | 🔴 FAILS as currently specified. The "effectively once" label is misleading without a formally defined recovery protocol. The achievable guarantee is **"at-least-once with best-effort deduplication"** unless the recovery protocol is formally specified as an application-layer invariant. |

---

### Claim 3 — "state_transitions table satisfies all auditability requirements"

| Field | Content |
| :--- | :--- |
| **CLAIM** | A single append-only `state_transitions` table captures sufficient audit information |
| **STATUS** | Survives with conditions |
| **ATTACK** | Polymorphic FK design. The `entity_id UUID FK` column cannot have a real database-enforced foreign key to multiple tables. If an `Article` or `ContentVersion` is deleted (even accidentally), the `state_transitions` records become orphans with no referential integrity enforcement. |
| **EVIDENCE** | PostgreSQL does not support polymorphic FK constraints natively. A `state_transitions.entity_id` without a concrete FK is an unconstrained UUID column. (FACT) |
| **COUNTEREXAMPLE** | `DELETE FROM content_versions WHERE id = $1` — if no application-level protection or soft-delete strategy exists, all associated `state_transitions` records become meaningless orphans. |
| **VERDICT** | 🟡 MINOR — The audit table design needs a defined referential integrity strategy (soft-delete on entities, or table-specific audit tables per aggregate). The core approach (append-only audit) survives. |

---

### Claim 4 — "Event Sourcing has zero additional benefit for the MVP"

| Field | Content |
| :--- | :--- |
| **CLAIM** | Event Sourcing provides zero additional benefit over the Hybrid approach |
| **STATUS** | Rejected as stated; directional conclusion survives |
| **ATTACK** | The claim "zero benefit" is factually incorrect and weakens the analysis. Event Sourcing has three genuine benefits not provided by the hybrid approach: (1) structural audit enforcement (audit cannot be skipped — every state change IS an event), (2) native crash recovery (if the event is stored, the effect is reproducible), (3) causal chain queryability (not just "what happened" but "why, from which event"). |
| **EVIDENCE** | In Event Sourcing, there is no "audit table neglect" risk because the event IS the state. (FACT). In the hybrid model, a developer can change state without inserting into `state_transitions` — and the database will not prevent it. |
| **VERDICT** | 🟡 MINOR — "Zero benefit" must be corrected to "benefits do not justify MVP complexity." Event Sourcing is still correctly rejected. The rejection rationale is weak, not the rejection decision. |

---

## 4. F-001 — Atomicity Analysis (Deep Attack)

### The Real Question: What Is the Atomic Unit of a State Transition?

The analysis never formally answers this. This is an architectural gap, not an implementation detail.

In the JincSAE domain, a **state transition** is a business event. It has two mandatory components:

1. The state change itself (`UPDATE content_versions SET status = 'APPROVED'`).
2. The audit record of that change (`INSERT INTO state_transitions`).

These two operations are **semantically inseparable**. If one occurs without the other, the system is in an inconsistent state. There are three cases:

**Case 1: State changes but audit is not written**

- Operational impact: The business has no record of who approved what or when.
- Risk: Violates the Engineering Constitution's traceability requirement.
- Is this prevented? **No.** The analysis acknowledges it as a risk ("Audit table neglect") but provides no architectural enforcement. Saying "must be within the same transaction" is a guideline, not a guarantee.

**Case 2: Audit is written but state does not change**

- Operational impact: The audit log shows an approval that never happened.
- Risk: False audit record; downstream workers may skip re-processing.
- Is this prevented? **No.** If the application inserts into `state_transitions` before the CAS UPDATE (and the UPDATE fails), the audit record already exists.

**Case 3: Both succeed but in separate connections**

- Operational impact: Crash window between `UPDATE` commit and `INSERT` commit.
- Risk: State is changed (committed to DB), audit never written.
- Is this prevented? **No.** Not unless the Repository explicitly wraps both in a single `BEGIN ... COMMIT` block.

### What Would Prevent All Three Cases?

A **mandatory explicit transaction boundary at the Use Case layer**, where both the CAS UPDATE and the state_transitions INSERT are wrapped in the same database transaction. This is an achievable guarantee in SQLAlchemy via async context managers:

```python
async with session.begin():  # <-- explicit transaction demarcation
    rows = await session.execute(cas_update)
    if rows.rowcount == 0:
        raise StateConflictError()
    await session.execute(audit_insert)
```

The analysis does not mandate this. The Repository Abstraction section (§12) only says models should be in the `infrastructure` layer. It does not say "every state transition port method must wrap both operations in a single transaction."

**Red Team Verdict on F-001:** 🟠 **MAJOR GAP.** The analysis must explicitly define that the atomic unit of a state transition = (CAS UPDATE + state_transitions INSERT) within a single database transaction, and that this is an application-layer invariant, not an implementation suggestion. Without this, the concurrency safety claims are aspirational, not architectural.

---

## 5. F-002 — Publication Semantics Analysis (Protocol Falsification)

### Precisely What Guarantee Is Achievable?

Let us define the publication protocol as described in the analysis and then attack each step.

**Described Protocol (reconstructed from §4.E, §8, §9, §10):**

1. CAS: `UPDATE content_versions SET status = 'SCHEDULED' WHERE id = $1 AND status = 'APPROVED'`
2. INSERT a new `PublicationAttempt` record
3. Call the external platform API
4. On success: UPDATE `publication_attempts SET status = 'SUCCESS', external_publication_id = $id`
5. On recovery: check if any prior attempt has a non-null `external_publication_id`; if yes, skip

### Attack Sequence: The Timeout Ambiguity Scenario

```
Worker claims content (APPROVED → SCHEDULED). ✓ DB committed.
Worker creates PublicationAttempt #1. ✓ DB committed.
Worker calls LinkedIn POST /shares.
LinkedIn receives the request.
LinkedIn processes the post.
LinkedIn returns HTTP 200 with { post_id: "urn:li:share:123456" }.
Network connection drops. Worker never receives the 200.
Worker catches a ConnectionError (or ReadTimeout).
Worker does not know: did LinkedIn publish or not?
```

At this point:

- `content_versions.status = SCHEDULED` (no change)
- `publication_attempts.status = IN_PROGRESS` or `PENDING` (no update to SUCCESS)
- `publication_attempts.external_publication_id = NULL`
- LinkedIn has published the content.

**Recovery Sequence:**

```
Recovery worker scans for SCHEDULED content versions.
Finds content_version_id = X, status = SCHEDULED.
Finds publication_attempt_id = #1, external_publication_id = NULL.
Guard condition: no successful attempt found.
Recovery worker creates PublicationAttempt #2.
Recovery worker calls LinkedIn POST /shares again.
LinkedIn publishes a DUPLICATE post.
```

**The guard failed because the ID was never stored.** The "effectively once" claim collapses in this scenario.

### What Would Actually Prevent This?

There are two real approaches:

**Approach A — External Idempotency Key (if supported by platform)**
Before calling the external API, generate a stable, deterministic idempotency key (e.g., `SHA256(content_version_id + attempt_number)`). Pass this key in the API request (e.g., LinkedIn's `X-Idempotency-Key` header if supported). If the platform supports it, a duplicate POST with the same idempotency key returns the original result without creating a duplicate.

- **LinkedIn:** Supports idempotency keys on some API versions. (FACT for selected endpoints — requires verification per platform)
- **Instagram Graph API:** Does not expose a generic idempotency key mechanism for posts. (FACT)
- **Bluesky AT Protocol:** Does not currently expose a post-level idempotency key. (FACT)
- **Facebook Graph API:** Does not expose a generic idempotency key for posts. (FACT)

**Verdict:** External idempotency keys are platform-dependent and cannot be the universal solution. The analysis does not assess platform-specific API capabilities. This is a MISSING ANALYSIS for a system that publishes to four different platforms.

**Approach B — Intermediate "PUBLISHING" State**
Introduce a transient state between `SCHEDULED` and `PUBLISHED`:

```
SCHEDULED → PUBLISHING → PUBLISHED
                └──→ PUBLISH_FAILED
```

The `PUBLISHING` state means: "an attempt is currently in flight." On crash recovery, a worker finding `status = PUBLISHING` knows an in-flight attempt exists. It can:

1. Query the external platform to check if the post exists (if the platform supports a lookup by idempotency key or content fingerprint).
2. Or: wait for a timeout window before retrying (treating the in-flight attempt as potentially successful).

This does not eliminate the ambiguity, but it makes the "gray zone" **explicitly visible in the state machine**, rather than burying it in the `PublicationAttempt.external_publication_id = NULL` condition.

**Verdict on "effectively once":**

The analysis uses the term "effectively once" without formal definition. The achievable guarantee is:

> **"At-least-once dispatch with best-effort deduplication, where deduplication depends on successfully storing the external platform response before a crash."**

This is a weaker guarantee than "effectively once" implies. It should be stated honestly.

**Red Team Verdict on F-002:** 🟠 **MAJOR GAP.** The analysis must: (1) introduce a `PUBLISHING` intermediate state or equivalent, (2) formally define the recovery protocol order of operations, (3) acknowledge that "effectively once" is achievable only if the external platform provides an idempotency key mechanism, and (4) honestly label the guarantee for platforms that do not (e.g., Instagram) as "at-least-once with best-effort deduplication."

---

## 6. F-003 — Audit Integrity Analysis

### Polymorphic FK — Full Attack

The `state_transitions` table design is:

```
entity_type TEXT  (e.g., 'content_version')
entity_id   UUID  (FK — but not enforced)
```

**Attack vectors:**

1. **No referential integrity:** PostgreSQL cannot enforce `state_transitions.entity_id REFERENCES content_versions(id)` when `entity_id` can also reference other tables. If a `ContentVersion` row is deleted (bug, test, data migration), its `state_transitions` records become silent orphans. The DB will not prevent this.

2. **Type mismatch is silent:** If a developer inserts `entity_type = 'publication_attempt', entity_id = <some_content_version_uuid>`, the DB will accept it. No constraint prevents this cross-entity contamination.

3. **Query complexity:** `SELECT * FROM state_transitions WHERE entity_type = 'content_version' AND entity_id = $1` requires two filter conditions on every query, adding cognitive overhead and potential index design complexity.

### Alternatives Comparison

| Design | Referential Integrity | Query Simplicity | Implementation Overhead |
| :--- | :---: | :---: | :---: |
| Single polymorphic `state_transitions` | ❌ None (unconstrained UUID) | Medium | Low |
| Separate `content_version_transitions` table | ✅ Real FK to `content_versions` | High | Medium |
| Per-aggregate audit columns (created_at, actor) | ✅ N/A (embedded) | High | Very Low |
| `actor_type + actor_id nullable` | N/A (attribute design) | N/A | Low |

### Actor Identity Gap

Transitions `GENERATED → VALIDATED` have no human actor — they are system-automated. The current design shows `actor_id TEXT`, which implies a single actor model.

The SDD §14 leaves authentication UNDECIDED. This means `actor_id` for human transitions has no defined format. For system transitions, there is no defined concept of a "system principal."

**Concrete issue:** If `actor_id` is NULL for system transitions and required for human transitions, this constraint is not enforced by the schema as designed. A developer can insert any string or NULL.

**Verdict on F-003:** 🟡 **MINOR** — The polymorphic FK design is architecturally weak for a system that mandates auditability. The recommendation should move to per-aggregate audit tables (e.g., `content_version_transitions`) with real FK constraints. The actor model requires at minimum: `actor_id (nullable UUID)`, `actor_type ENUM('human', 'system', 'worker')` to correctly represent the full range of state-changing actors.

---

## 7. F-004 — Event Sourcing Counterfactual

### The Best Case FOR Event Sourcing in JincSAE

The analysis dismissed Event Sourcing with "zero additional benefit." This is factually wrong. Let me construct the strongest argument for it:

**Structural Audit Enforcement:** In the hybrid model, the application can change `content_versions.status` without touching `state_transitions`. The database will not prevent this — it's an application discipline requirement. In an event-sourced model, there is no "status column" to update — the current state IS derived from events. You cannot have state divergence from audit because there is only one source of truth: the event stream.

**Native Crash Recovery for Publication:** If the event `PublicationAttemptDispatched` is stored to the event store BEFORE the external API call, replay semantics are clear: on recovery, the event exists, so the system knows an attempt was made. Compare this to the hybrid model where the crash window (between external call and `external_publication_id` storage) creates ambiguity.

**Causal Chain as First-Class Citizen:** The SDD mandates `Article → Brief → ContentVersion → PublicationAttempt` traceability. In an event-sourced system, causality is encoded as `causation_id` on every event — each event references the event that caused it. This makes investigative queries ("why was this published?") trivially answerable.

**Now the attack on Event Sourcing itself:**

1. **Projection consistency:** Current-state queries (e.g., "all ContentVersions PENDING_REVIEW") require projections that are rebuilt from events. In a synchronous Python MVP without dedicated projection infrastructure, this introduces read complexity that the team must manage.

2. **Event schema evolution:** If the system runs for 6 months and the `ContentVersionApproved` event schema needs a new field, older events in the store are immutable. Versioning strategy (upcasting, versioned events) must be designed upfront — it cannot be retrofitted.

3. **Operational debugging:** When an editor asks "why is this content stuck?", the answer requires replaying events. Without tooling, this is harder than a simple `SELECT * FROM content_versions WHERE id = $1`.

4. **PRD does not evidence temporal query requirements.** The primary justification for Event Sourcing (temporal queries: "what was the state at time T?") has no PRD requirement. The audit questions in §4.F are all point-in-time questions (who approved? how many attempts?), answerable by an audit table.

**Final Assessment of Event Sourcing Rejection:**

The rejection stands, but for the correct reasons: the benefits (structural audit enforcement, native crash recovery) are real but the implementation complexity is disproportionate to the MVP scope and PRD requirements. Specifically:

- Structural audit enforcement can be achieved through mandatory transaction boundary discipline (FINDING-001 fix) without full Event Sourcing.
- Native crash recovery gap (FINDING-002) should be addressed by introducing a `PUBLISHING` state and a formal recovery protocol, not by adopting Event Sourcing.

**Revised rejection language:** "Event Sourcing provides genuine benefits in audit enforcement and crash recovery that are not fully captured by the hybrid model. However, these benefits are achievable at lower complexity cost through explicit transaction boundary discipline and a formally defined publication recovery protocol. Event Sourcing is rejected for the MVP."

---

## 8. Failure Scenario Matrix

| Scenario | Current Design Response | PASS/PARTIAL/FAIL | Required Mitigation |
| :--- | :--- | :---: | :--- |
| S1: Duplicate Webhook | Unique constraint on `(source_id, wp_post_id)` | ✅ PASS | None |
| S2: Concurrent Approval | CAS `WHERE status = PENDING_REVIEW` | ✅ PASS | Must be in explicit transaction with audit INSERT |
| S3: Regeneration Race (editor approves while another requests regen) | No CAS guards regeneration request against existing PENDING_REVIEW | ⚠️ PARTIAL | Must define: can regeneration be requested while content is PENDING_REVIEW? State machine must be explicit |
| S4: Audit Failure (state changes, audit not written) | No architectural enforcement | ❌ FAIL | Mandatory transaction boundary enclosing CAS + audit INSERT |
| S5: Worker Crash Before Publish | Content stays SCHEDULED; recovery re-dispatches | ✅ PASS | No duplicate; content was never externally published |
| S6: Worker Crash After Remote Success | external_publication_id never stored; recovery publishes duplicate | ❌ FAIL | Introduce PUBLISHING state; define recovery query order; assess platform idempotency keys |
| S7: Timeout Ambiguity | Ambiguous; no PUBLISHING state to signal in-flight | ❌ FAIL | PUBLISHING intermediate state required to make the ambiguous zone visible |
| S8: Retry Storm | CAS on SCHEDULED prevents multiple claims | ✅ PASS | None — CAS acts as a lock for the SCHEDULED state |
| S9: Manual Recovery After Permanent Failure | Not analyzed; no defined manual intervention protocol | ⚠️ PARTIAL | Define state for permanently failed content; define admin action required |
| S10: Historical Investigation (6 months later) | state_transitions + publication_attempts cover most audit questions | ✅ PASS | With caveats: orphan risk (FINDING-003); actor_id format dependency |

**Summary:** 5 PASS, 2 PARTIAL, 3 FAIL

---

## 9. Assumptions Proven False

1. **"CAS is sufficient for concurrency safety of state transitions"** — FALSE as a standalone claim. CAS protects single-row updates; multi-table atomicity requires explicit transaction demarcation.

2. **"effectively once is achievable via external_publication_id guard"** — FALSE as an unconditional claim. Achievable only if the `external_publication_id` is successfully written before any retry window. The crash window between external API success and DB write makes this non-guaranteed.

3. **"Event Sourcing has zero additional benefit"** — FALSE. It has real structural audit enforcement and native crash recovery benefits. The rejection is correct but the stated rationale is not.

4. **"`state_transitions` with polymorphic FK provides referential integrity"** — FALSE. PostgreSQL cannot enforce a polymorphic FK. Records become unconstrained orphans.

---

## 10. Assumptions That Survived

1. **PostgreSQL is the correct persistence technology for this domain.** The relational data model (Article → Brief → ContentVersion → Approval → Publication) maps naturally to a relational schema. ACID transactions, unique constraints, and conditional UPDATE are sufficient tools for the primary concurrency scenarios. This holds.

2. **MongoDB is not appropriate for JincSAE.** Cross-collection ACID transactions for multi-entity workflows are more complex in MongoDB than in PostgreSQL for this specific domain. This holds.

3. **Event Sourcing is too complex for the MVP.** The PRD does not justify the additional complexity. The audit and traceability requirements can be met with simpler tools when the protocol gaps (F-001, F-002) are resolved. This holds.

4. **SQLAlchemy 2.x with asyncpg is the correct Python ORM strategy.** Given ADR-001 (Python), this is the mature, well-supported choice. SQLModel risks domain-infrastructure coupling. Raw SQL adds boilerplate. This holds.

5. **Append-only PublicationAttempt records are the correct model for publication tracking.** Each attempt is a distinct business event with its own identity, timestamps, and result. This holds — PublicationAttempt is NOT a state transition; it is a separate entity.

6. **Ingestion idempotency via unique constraint is correct.** This is a standard, proven, and crash-safe pattern. This holds.

---

## 11. Architecture Changes Required

### 🟠 MAJOR — M-001: Mandatory Transaction Boundary Invariant

**What:** Define as an explicit architectural invariant that every state transition in the JincSAE persistence layer must wrap the CAS UPDATE and the `state_transitions` INSERT within a single database transaction. This must be specified at the Repository Port definition level, not left to implementation discretion.

**Impact:** Affects data access strategy (§12), architectural invariants (§5), and repository abstraction recommendation.

---

### 🟠 MAJOR — M-002: Publication Protocol Formal Specification + PUBLISHING State

**What:** Introduce an explicit `PUBLISHING` intermediate state in the content version state machine. Define the formal publication recovery protocol as:

1. Claim: CAS `APPROVED → SCHEDULED`.
2. Dispatch: CAS `SCHEDULED → PUBLISHING` immediately before external call.
3. Call external API.
4. On success: CAS `PUBLISHING → PUBLISHED` + store `external_publication_id`.
5. On failure/timeout: CAS `PUBLISHING → PUBLISH_FAILED` (or leave as PUBLISHING for timeout cases with defined TTL).
6. Recovery protocol (explicit): For any `PUBLISHING` content version beyond TTL — query `PublicationAttempts` for non-null `external_publication_id`. If found → mark PUBLISHED. If not → create new attempt, CAS `PUBLISHING → SCHEDULED` to reset.

**Impact:** State machine in SDD §10 must acknowledge this state. The analysis must note this as a proposed state machine refinement (not a change to the SDD, which is accepted, but an explicit clarification).

---

### 🟡 MINOR — M-003: Per-Aggregate Audit Tables or Explicit Orphan Protection

**What:** Replace the polymorphic `state_transitions` design with either:

- Per-aggregate tables: `content_version_transitions (id, content_version_id FK, from_state, to_state, actor_id, actor_type, timestamp, reason)` — enforces real FK.
- Or: retain the polymorphic design but mandate a soft-delete strategy on all auditable entities (never hard-delete; always set `deleted_at`).

**Impact:** Schema design only. Does not change persistence strategy direction.

---

### 🟡 MINOR — M-004: Actor Model Specification

**What:** Define the `actor` concept before schema design begins. At minimum: `actor_id (nullable UUID)`, `actor_type ENUM('human', 'system', 'background_worker')`. System transitions have no `actor_id` (nullable). Human transitions have a `actor_id` that resolves once the Authentication ADR is accepted.

**Impact:** Schema design dependency. Does not block the persistence strategy decision.

---

### 🟡 MINOR — M-005: Correct Evidence Label for Event Sourcing Rejection

**What:** Replace "zero additional benefit" with "genuine benefits (structural audit enforcement, native crash recovery) do not justify MVP complexity when alternative mitigations are available."

**Impact:** Documentation quality only.

---

### 🔵 OBSERVATION — O-001: Platform Idempotency Key Assessment

**What:** Before finalizing the publication protocol, research whether LinkedIn, Instagram, Facebook, and Bluesky expose idempotency key mechanisms for post creation. If they do, these should be used as the primary deduplication mechanism. If they do not, the "best-effort deduplication" honest label must be applied per platform.

**Impact:** Informs the final publication protocol design in a future implementation specification.

---

### 🔵 OBSERVATION — O-002: Regeneration Race Condition (Scenario S3)

**What:** The state machine does not define whether regeneration is permitted from `PENDING_REVIEW` state. If it is, a race condition exists where one editor approves while another requests regeneration. The CAS guard for approval will succeed before the regeneration request is processed, leaving the system with an approved version and a pending regeneration request for the same brief/platform.

**Impact:** This is a domain modeling question, not a persistence question. It should be documented as an open question for the Domain Specification.

---

## 12. Alternative Architecture Comparison

Only the two architecturally relevant alternatives are compared given the Red Team findings.

### Alternative 1: PostgreSQL + Formal Transaction Boundary + PUBLISHING State (Revised Option D)

This is the recommended direction after mitigations. All current design strengths preserved. F-001 and F-002 resolved via explicit protocol specification, not infrastructure change.

### Alternative 2: Event Sourcing

As analyzed in §7, Event Sourcing eliminates F-001 (audit divergence) structurally and reduces F-002 (crash recovery) complexity by making the event record the primary source of truth. However, it introduces projection infrastructure, event schema versioning, and operational debugging complexity not justified by the MVP PRD.

**Verdict:** Alternative 2 remains rejected. It should be noted as a viable evolution path if the system's audit and recovery requirements grow beyond what the formal protocol mitigation can handle.

---

## 13. Red Team Recommendation

**The database strategy (PostgreSQL) is correct. The protocol is underspecified.**

The ADR-002 Analysis must be revised to:

1. Formally define multi-table atomicity as a mandatory architectural invariant.
2. Introduce the `PUBLISHING` intermediate state and formally specify the publication recovery protocol.
3. Revise the "effectively once" claim to "at-least-once with best-effort deduplication" for platforms that lack idempotency keys.
4. Replace or harden the polymorphic `state_transitions` design for referential integrity.
5. Correct the Event Sourcing rejection rationale.

Once these revisions are made, the analysis is eligible for acceptance. The changes are **revisions to the protocol specification, not to the fundamental architecture direction.**

---

## 14. Required Reconciliation Questions

The following questions require reconciliation before the ADR can be accepted:

| # | Question | Classification | Blocks Acceptance? |
| :--- | :--- | :--- | :---: |
| R1 | Is `PUBLISHING` an explicit state in the state machine, or is it handled as an implicit in-flight condition? | Architectural Decision | ✅ Yes |
| R2 | Is the mandatory transaction boundary (CAS + audit INSERT) specified at the Repository Port level or left to implementation? | Architectural Invariant | ✅ Yes |
| R3 | Is the audit table polymorphic (single table) or per-aggregate (separate FKs)? | Schema Design Direction | ✅ Yes |
| R4 | What is the actor model for system-initiated vs. human-initiated transitions? | Schema Design Direction | No (post-Auth ADR) |
| R5 | Do the target social platforms (LinkedIn, Instagram, Facebook, Bluesky) expose idempotency keys for post creation? | Platform Research | No (informs implementation) |
| R6 | Is regeneration permitted from `PENDING_REVIEW` state, and if so, what CAS guards prevent the approval/regeneration race? | Domain Modeling | No (Domain Spec) |
