# ADR-002 Decision Readiness Review

**Artifact Reviewed:** `docs/adr/ADR-002-Reconciliation.md`  
**Date:** 2026-08-31  
**Purpose:** Determine if the Reconciliation Brief is correctly scoped for human decision — not too broad, not too narrow, no false choices, no hidden implementation details dressed as executive decisions.

> This document does not take any decision. It audits whether the decision package is clean.

---

## 1. Executive Verdict

**READY WITH DECISION REFINEMENT**

The Reconciliation Brief is technically sound and the analysis is correct. However, it presents **5 pending items as if all 5 require independent human decisions**. Upon examination, only **2 of the 5 are genuine human decisions**. The remaining 3 are either already determined by authoritative documents, are architectural consequences of the primary decision, or are implementation details that should be deferred to downstream specifications.

Presenting 5 items conflates executive decision-making with architectural interpretation, which increases cognitive load on the decision-maker without adding decision value. The package should be refined before submission.

---

## 2. Decision Classification Matrix

| Pending Item | Classification | Human Decision Required? | Reason |
| :--- | :--- | :---: | :--- |
| **A. PostgreSQL + Hybrid Audit** | ✅ TRUE HUMAN DECISION | Yes | This is the core strategic choice. No authoritative document mandates a specific DB. SDD §17 names PostgreSQL as a "strong candidate" — not a decision. The analysis, Architecture Review, and Red Team converge technically, but the human must formally accept. |
| **B. Audit tables by aggregate with real FK** | 🔶 ARCHITECTURAL CONSEQUENCE | No (Deferred) | If PostgreSQL + Hybrid Audit is accepted (Decision A), the audit mechanism is an implementation concern. The principle "audit history is required with referential integrity" is constitutionally mandated. The specific schema (per-aggregate table vs. polymorphic with soft-delete) is a downstream implementation decision, not an executive ADR-level choice. |
| **C. PUBLISHING state + Recovery Protocol** | ⚠️ ALREADY DETERMINED | No | The Engineering Constitution §14 explicitly includes `PUBLISHING` in its state machine example. This is not a decision open to the human — it is already determined by the highest-authority document. The Reconciliation correctly notes this (Section 7, M-002), but then incorrectly re-presents it as a pending human choice in Section 19. The human need only be informed that PUBLISHING is constitutionally mandated. The recovery protocol specifics are an implementation detail for a future Domain/Feature Specification. |
| **D. Residual external side-effect risk accepted** | ✅ TRUE HUMAN DECISION | Yes | This is a genuine business/editorial risk acceptance. The duplicate-post risk is irremovable by the persistence architecture alone. Only the decision-maker can accept it on behalf of the organization. It is not a technical choice; it is a risk posture choice. |
| **E. Event Sourcing — REJECTED FOR MVP / RETAIN AS FUTURE OPTION** | 🔷 ARCHITECTURAL CONSEQUENCE | No | "Retain as Future Option" is not a decision — it is the default state of any rejected technology. Accepting PostgreSQL + Hybrid Audit (Decision A) implicitly closes Event Sourcing for the MVP scope. Presenting this as a separate human choice creates a false decision point. The human merely acknowledges the consequence, not makes a new choice. |

---

## 3. Coupled Decisions

### Coupling A → B → C

Items A (PostgreSQL), B (audit table design), and C (PUBLISHING state) are tightly coupled in the Reconciliation but presented as independent decisions.

The correct logical dependency is:

```
Decision A: Accept PostgreSQL + Hybrid Audit
         ↓
Architectural Consequence B: Audit tables with referential integrity
(principle locked; specific schema deferred to implementation)
         ↓
Already Determined C: PUBLISHING state
(Engineering Constitution §14 — not open for decision)
```

Presenting B and C as separate human choices forces the decision-maker to ratify implementation details and constitutional text. Neither should appear as an item in the Human Decision package.

### Coupling D ↔ A

Item D (residual risk acceptance) is genuine but only coherent in the context of Decision A being accepted. It should be presented as a rider to Decision A: "By accepting PostgreSQL + Hybrid Audit, you accept that the external publication side-effect risk is irremovable by the persistence layer."

### Event Sourcing as Consequence, Not Choice

Item E is a consequence of A. If A is accepted, E is implicitly closed. Asking the human to decide "REJECTED FOR MVP vs. RETAIN AS FUTURE OPTION" is a false dichotomy: any rejected technology is automatically a potential future option. It requires no separate choice.

---

## 4. Decisions That Should Be Deferred

The following items appear in ADR-002-Reconciliation.md but should NOT be locked at the ADR level:

| Item | Why It Should Be Deferred | Correct Home |
| :--- | :--- | :--- |
| Specific audit table schema (per-aggregate vs. polymorphic with soft-delete) | Implementation detail; depends on aggregate model finalization | Domain Specification / Schema Specification |
| Actor model concrete format (`actor_id` string format) | Explicitly depends on Authentication ADR (SDD §14 is PROPOSED - UNDECIDED) | Authentication ADR (future) |
| Recovery TTL value for PUBLISHING state | Operational parameter, not an architectural decision | Implementation / Operations Specification |
| Platform idempotency key assessment | Requires empirical research per platform; informs Publication Delivery ADR | Publication Delivery ADR (future) |
| Number and naming of per-aggregate audit tables | Follows from aggregate boundary decisions, not yet finalized | Domain Model Specification |

---

## 5. Evidence Gaps

The following evidence is absent and affects the precision of the decision package. These are not blocking (the decision can proceed), but the decision-maker should be aware of them:

| Gap | Impact | When Must It Be Resolved? |
| :--- | :--- | :--- |
| **Platform idempotency key support** (LinkedIn, Instagram, Facebook, Bluesky) | Determines whether "best-effort deduplication" can be upgraded to "effectively once" per platform. If all platforms lack idempotency keys, the residual risk is higher than if some support them. | Before Publication Delivery ADR. Does not block ADR-002. |
| **Authentication ADR (actor identity)** | The `actor_id` for `HUMAN` actors has no defined format. The concept is correct; the concrete form is unknown. | Authentication ADR (future). Does not block ADR-002. |
| **Aggregate boundary definition** | Per-aggregate audit tables cannot be definitively named until aggregate boundaries are defined (e.g., is `ContentVersion` within `Article` or a separate aggregate?). | Domain Model Specification. Does not block ADR-002. |
| **Concurrent editorial user count** | The analysis defaults to CAS (optimistic) over `SELECT FOR UPDATE` (pessimistic). If high-contention approval scenarios emerge from actual usage, this may need revision. PRD does not evidence high-concurrency requirements. | Not blocking — low risk given PRD scope. |

**Classification note:** None of these gaps block ADR-002 from proceeding to human decision. They inform downstream ADRs. The decision-maker should be told this explicitly.

---

## 6. Correct Human Decision Package

The 5-item decision list in ADR-002-Reconciliation.md §19 should be replaced with **2 decisions and 1 acknowledgment**:

---

### DECISION 1 — Persistence Strategy (TRUE HUMAN DECISION)

> **Accept PostgreSQL as the JincSAE MVP persistence technology, implementing a Hybrid Audit model (current-state tables + dedicated append-only audit history tables with referential integrity), with the following architectural invariants locked:**
>
> 1. Every state transition is the atomic unit of (CAS UPDATE + audit INSERT) within a single explicit database transaction.
> 2. State-transition audit tables use referential integrity strategies (per-aggregate tables or soft-delete mandate) — exact schema is a downstream implementation concern.
> 3. SQLAlchemy 2.x (async) with asyncpg is the data access technology.
> 4. Alembic is the migration tool.
> 5. Repository pattern (per-aggregate port interfaces) is mandatory.

**What this decision does NOT lock:** Audit table schema specifics, actor_id format, queue technology, ORM configuration details, publication delivery implementation.

---

### DECISION 2 — Residual Risk Acceptance (TRUE HUMAN DECISION)

> **Accept that the JincSAE persistence architecture cannot guarantee exactly-once delivery to external social media platforms. The achievable guarantee is at-least-once dispatch with best-effort deduplication via `external_publication_id` when successfully stored. When a publication call succeeds externally but the response is lost before the ID is stored, the system cannot prevent a duplicate post. This risk is accepted as an irremovable architectural boundary limitation, not a design failure.**

**This decision cannot be eliminated** by any persistence technology choice, including Event Sourcing, without external platform idempotency key support. It is a structural property of distributed systems where the JincSAE database and social media APIs cannot share a transaction.

---

### ACKNOWLEDGMENT — Constitutional State Machine (NOT A DECISION)

> **Note for the record:** The `PUBLISHING` intermediate state is explicitly included in the Engineering Constitution §14 state machine example. Its presence in the JincSAE architecture is constitutionally determined, not a choice open to ADR-002. The recovery protocol specifics are an implementation concern for a future Domain/Feature Specification.

This item should be removed from the human decision list and re-framed as a constitutional notice.

---

## 7. Residual Risk Acceptance — Precise Formulation

By proceeding with Decision 1 + Decision 2, the human decision-maker is accepting the following residual risks. These should be stated clearly, not buried:

| Risk | Nature | Frequency Estimate | Severity |
| :--- | :--- | :--- | :--- |
| Duplicate post on social platform | Structural; irremovable without platform idempotency keys | Rare — requires simultaneous external API success + response loss + retry | High impact if it occurs; low frequency expected |
| Audit history gap | Manageable with transaction discipline; not irremovable | Zero if transaction invariant is respected; non-zero if implementation violates it | High impact if occurs; preventable |
| Actor_id format migration | Deferred; requires Auth ADR; low risk of incompatibility if string field used | One-time migration risk after Auth ADR | Low |

**The human must explicitly accept the first risk** (duplicate post). It is editorial in nature and cannot be decided by technical analysis alone. A technical team can minimize it; only the organization can accept it.

The second and third risks are implementation-level and do not require explicit executive acceptance.

---

## 8. Final Recommendation

**ADR-002 can proceed to Human Acceptance** once the decision package is refined from 5 items to **2 decisions + 1 acknowledgment** as specified in Section 6.

The Reconciliation Brief's technical content is correct and complete. No additional review cycle is required. The refinement needed is presentational: collapse the decision list to remove architectural consequences and already-determined items, making the human decision surface as small and precise as possible.

**Workflow:**

```
ADR-002-Decision-Readiness.md (this document)
    ↓
Refine decision package to 2 decisions + 1 acknowledgment
    ↓
HUMAN DECISION
    ↓
Author ADR-002.md (final, ACCEPTED)
    ↓
ADR-003 (Queue/Async Strategy) — unblocked
ADR-004 (ORM/Data Access) — unblocked
```

**What must NOT happen:** The human should not be asked to decide audit table schema, actor_id format, recovery TTL, or platform idempotency keys at this stage. These are downstream concerns.
