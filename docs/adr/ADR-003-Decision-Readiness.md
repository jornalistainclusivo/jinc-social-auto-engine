---
adr-id: ADR-003
artifact-type: Decision Readiness Review
title: "ADR-003 — Decision Readiness Review"
status: ASSESSMENT COMPLETE
date: 2026-09-01
primary-source: docs/adr/ADR-003-Reconciliation.md
produced-by: Architecture Decision Readiness Board
  roles:
    - architect-review (Lead — independent readiness assessment)
    - architecture-decision-records (decision integrity)
    - senior-architect (systemic consistency)
    - database-architect (transactional evidence review)
---

# ADR-003 Decision Readiness Review

---

## 1. Purpose

This review determines whether `docs/adr/ADR-003-Reconciliation.md` is ready
for a human architectural decision. It does not re-examine the architecture.
It examines the **quality of the evidence** and the **structure of the decision**
as presented to the human architect.

Three questions are answered:

1. Is the evidence complete enough to make a decision?
2. Is the decision correctly scoped (genuine human choices vs. consequences)?
3. What is the minimum required step before the decision can be made?

---

## 2. Evidence Reviewed

The following artifacts were reviewed in order of authority:

| # | Document | Role in this Review |
| :--- | :--- | :--- |
| 1 | `ENGINEERING_CONSTITUTION.md` | Absolute constraint baseline |
| 2 | `SDD.md` | System requirements baseline |
| 3 | `ADR-001-Runtime-Language.md` | Accepted constraint (not reopened) |
| 4 | `ADR-002-Persistence-Strategy.md` | Accepted constraint (not reopened) |
| 5 | `ADR-003-Analysis.md` | Original analysis |
| 6 | `ADR-003-ArchReview.md` | Architecture review (CONDITIONAL) |
| 7 | `ADR-003-Analysis-Revised.md` | Remediated analysis |
| 8 | `ADR-003-RedTeam.md` | Red Team (HOLDS WITH MATERIAL REVISIONS) |
| 9 | `ADR-003-Reconciliation.md` | **Primary subject of this review** |

---

## 3. Executive Verdict

### 🟡 READY ONLY AFTER GATE 1 VALIDATION

**The ADR-003 Reconciliation is structurally sound. The recommendation of Option A
is methodologically defensible. However, the ADR must not be marked ACCEPTED —
and the human architectural decision should not be formally registered — before
Gate 1 (Transactional Enqueue Integration Test) produces a binary result.**

**Reason:** Gate 1 validates the central differentiating capability of Option A —
the only claim that separates it from all other candidates on the critical Driver 3
dimension. Gate 1's outcome does not change whether Option A is preferred, but it
does change WHAT the human is deciding. The human must know which implementation
pattern they are accepting before registering the decision.

**This is not a rejection of the Reconciliation.** The Reconciliation document is
well-constructed and correctly scoped. The verdict reflects the methodological
standard that an ACCEPTED ADR must not contain UNKNOWN central claims that remain
unvalidated at acceptance time.

**Gate 1 is a short-horizon validation** (one day of engineering work with a working
PG + SQLAlchemy async environment). The review board recommends proceeding to Gate 1
immediately, with the expectation that its result will enable a same-week ADR acceptance.

---

## 4. Human Decision Audit

The Reconciliation claims there are "5 genuine human decisions" (HD-1 through HD-5).
This claim is audited independently below.

| ID | Proposed Decision | Actual Classification | Human Decision Required? | Reasoning |
| :--- | :--- | :--- | :---: | :--- |
| **HD-1** | Accept Option A as primary queue strategy (conditional on Gate 1) | **TRUE HUMAN ARCHITECTURAL DECISION** | ✅ YES | Selection of async framework is a genuine architectural commitment with non-trivial reversal cost. Cannot be derived from Constitution, SDD, ADR-001, or ADR-002. |
| **HD-2** | Accept the coupled-availability trade-off (PG outage = queue outage) | **ARCHITECTURAL CONSEQUENCE** | ❌ NO | ADR-002 accepted PostgreSQL as the exclusive persistence layer. A queue that uses PostgreSQL natively inherits its availability profile by construction. This is not a new decision — it is a logical consequence of the already-accepted ADR-002. Presenting it as HD overstates the human's choice set. |
| **HD-3** | Proceed to Gate 1 now, or defer | **VALIDATION SEQUENCING CHOICE** | ⚠️ PARTIAL | This is a project management decision, not an architectural one. It does not belong in an ADR as a human decision. However, it is the **most operationally important choice** at this moment: the board recommends it be explicit, but framed as "when to execute Gate 1" rather than an architectural option. |
| **HD-4** | Accept Procrastinate's community/maturity risk | **RESIDUAL RISK ACCEPTANCE** | ✅ YES | This is a genuine human judgment call. The documented migration path (→ TaskIQ) reduces the cost, but the decision to accept or avoid this risk belongs to the human architect. It cannot be derived from architectural analysis alone. |
| **HD-5** | If Gate 1 fails, accept Option B-TaskIQ as fallback | **DEFERRED CONTINGENT DECISION** | ❌ NO (now) | This decision is contingent on Gate 1 failing. Asking the human to pre-commit to the fallback now is premature. If Gate 1 fails, a new human decision will be triggered with the relevant evidence. Presenting HD-5 now creates a false sense of resolution on a contingency that has not materialized. |

**Corrected decision count: 2 genuine human architectural decisions (HD-1, HD-4).**

**The Reconciliation's "5 decisions" claim is overstated by 3 items.** Two items are
architectural consequences (HD-2) and deferred/contingent decisions (HD-5), and one
is correctly called out as important but is a sequencing choice, not an architectural decision (HD-3).

### Corrected Human Decision Summary

**HD-1 (True):** Accept Option A — Procrastinate — as the async job engine for JincSAE.
*(Subject to Gate 1 validation of the transactional integration pattern.)*

**HD-4 (True):** Accept the Procrastinate community/maturity risk, with the documented
migration path to TaskIQ as the acknowledged contingency.

These are the two decisions the human architect must make. Everything else is consequence,
constraint, or deferred decision.

---

## 5. Gate 1 Materiality Analysis

### 5.1 Definition

Gate 1 (Transactional Enqueue Integration Test) validates whether Procrastinate's
`defer_async()` can participate in the same PostgreSQL transaction as SQLAlchemy's
`AsyncSession` in the JincSAE stack, such that:

- Domain transaction rollback → job does not exist in `procrastinate_jobs`
- Domain transaction commit → job exists in `procrastinate_jobs`

### 5.2 If Gate 1 PASSES

| Claim | Status After PASS |
| :--- | :--- |
| "Transactional Dispatch Invariant is achievable" | ✅ VERIFIED FACT |
| "S3 prevention is structural (not merely compensating)" | ✅ VERIFIED — when invariant correctly implemented |
| Option A Driver 3 score: **4** | ✅ Confirmed |
| Option A total: **115** | ✅ Confirmed |
| The exact connection-sharing API pattern | ✅ Documented as reference implementation |
| Architectural invariant AI-001 | ✅ Becomes a formal invariant (not a candidate) |

**After Gate 1 PASS: Option A is accepted on its stated terms. The ADR can be
immediately marked ACCEPTED. No further architectural analysis is required.**

### 5.3 If Gate 1 FAILS

A Gate 1 failure means that connection sharing between Procrastinate and SQLAlchemy
async is not achievable in the JincSAE stack without unacceptable complexity. This
eliminates the direct transactional integration pattern.

**Does Gate 1 failure eliminate S3 prevention entirely?**

**No.** S3 prevention remains achievable through the Transactional Outbox pattern:

| Component | Role |
| :--- | :--- |
| Domain transaction | CAS UPDATE + audit INSERT + outbox row INSERT (all in same PG transaction) |
| Outbox table | PostgreSQL table; rows are INSERT-ed within the domain transaction |
| Relay process | Reads committed outbox rows; calls Procrastinate `defer_async()` via its own connection |

This pattern is architecturally sound and well-established. It restores atomic S3 prevention
within the PostgreSQL ecosystem. However, it adds:

- One additional table (outbox)
- One additional process component (relay)
- Additional implementation complexity

**Does Gate 1 failure change Option A's candidate ranking?**

| Dimension | Gate 1 PASS | Gate 1 FAIL |
| :--- | :--- | :--- |
| Driver 3 score (Option A) | 4 | **2** (direct integration lost) |
| S3 prevention available? | ✅ Direct | ✅ Via Outbox pattern |
| Additional services required | 0 | 0 (outbox relay is in-process or separate) |
| Option A total | 115 | **109** |
| TaskIQ total | 97 | 97 |
| Option A still preferred? | ✅ Yes (gap: 18) | ✅ Yes (gap: **12**) |

**Gate 1 failure does NOT change candidate ranking. Option A remains preferred at 109 vs. TaskIQ's 97.**

**Does Gate 1 failure materially change the architecture?**

**YES — in a specific and important way.**

The architecture changes from:

```
Domain Transaction:
    CAS UPDATE + audit INSERT + defer_async()  [1 transaction]
```

to:

```
Domain Transaction:
    CAS UPDATE + audit INSERT + outbox INSERT  [1 transaction]
Relay:
    outbox read → defer_async()               [separate operation, eventual]
```

The human architect must know which pattern they are accepting. These are materially
different implementation architectures — not merely different "how to configure Procrastinate."

**This is why the ADR must not be marked ACCEPTED before Gate 1 produces its result.**
The human is not deciding between "Procrastinate with connection sharing" and "Procrastinate
without connection sharing." They are deciding which implementation architecture to commit to.

### 5.4 Gate 1 Materiality Classification

| Dimension | Classification |
| :--- | :--- |
| Does Gate 1 failure change candidate ranking? | **NO** — Option A remains preferred |
| Does Gate 1 failure change S3 prevention capability? | **NO** — Outbox pattern provides equivalent guarantee |
| Does Gate 1 failure change the implementation architecture? | **YES — MATERIALLY** |
| Does Gate 1 failure change development effort? | **YES** — Outbox relay adds implementation surface |
| Does Gate 1 failure change operational complexity? | **MARGINALLY** — outbox relay is an additional concern |
| Is Gate 1 validating an implementation detail? | **NO — It validates the architectural pattern** |
| Is Gate 1 validating a central claim of the recommendation? | **YES** |

**Gate 1 classification: VALIDATES A CENTRAL ARCHITECTURAL PATTERN.**

Not merely an implementation detail. The pattern the team implements (direct
transactional integration vs. Outbox relay) is an architectural decision, not
a configuration choice. Human decision must follow Gate 1 result.

---

## 6. Conditional Acceptance Analysis

Three acceptance statuses were evaluated:

### Option 1: PROPOSED FOR HUMAN DECISION (Gate 1 executes first)

**Methodological validity: HIGH.**

The human decision is made with complete evidence. The ADR accurately reflects
what is being decided. Gate 1 result is known before acceptance. The accepted ADR
contains no UNKNOWN central claims.

**Trade-off:** Delays formal acceptance by the duration of Gate 1 execution (estimated:
1–2 engineering days with an available PostgreSQL + SQLAlchemy async environment).

**Board assessment:** This is the methodologically correct path. Gate 1 is short-horizon.
The delay is minimal. The quality of the accepted decision is maximum.

---

### Option 2: ACCEPTED WITH VALIDATION CONDITION (Option A accepted now, Gate 1 before implementation)

**Methodological validity: CONDITIONAL.**

In standard ADR practice, "accepted with condition" is used when the condition validates
an implementation detail, not an architectural pattern. The condition being validated
here (connection-sharing pattern) IS an architectural pattern — it determines whether
the architecture uses direct integration or an Outbox relay.

A reasonable argument for Option 2:

> "Even if Gate 1 fails, Option A remains the recommended candidate. The fallback
> (Outbox pattern) is still within the Procrastinate + PostgreSQL architecture. The
> candidate selection decision (Option A vs. all others) is stable regardless of Gate 1.
> Therefore, the technology decision can be accepted now; the implementation pattern
> decision can be deferred to Gate 1."

**This argument is valid under one condition:** The ADR must be scoped to "Option A
(Procrastinate + PostgreSQL) is the technology selection" — not to a specific
implementation pattern. The implementation pattern (direct vs. Outbox) must be
explicitly left open in the accepted ADR body.

**If the accepted ADR claims transactional dispatch without verification, it contains
a false claim at acceptance time. This is architecturally irresponsible.**

**If the accepted ADR correctly scopes the decision to technology selection and explicitly
leaves the integration pattern to Gate 1, then Option 2 is methodologically acceptable.**

**Board assessment:** Option 2 is defensible if and only if the ADR body is scoped to
"Procrastinate as the technology" without claiming the specific integration pattern.
This requires minor revision to the accepted ADR template.

---

### Option 3: ACCEPTED (No unresolved validation)

**Methodological validity: INVALID.**

The Reconciliation correctly classifies transactional enqueue as `UNKNOWN / REQUIRES
INTEGRATION VALIDATION`. Marking ACCEPTED while acknowledging an UNKNOWN central
claim is an evidential contradiction. This option is rejected.

**An accepted ADR that contains UNKNOWN central architectural claims is not a decision — it is a hope.**

---

### Conditional Acceptance Summary

| Option | Valid? | Condition |
| :--- | :--- | :--- |
| Option 1 (Gate 1 first) | ✅ Fully valid | No conditions |
| Option 2 (Accept now, validate before implementation) | ⚠️ Conditionally valid | ADR must NOT claim direct transactional integration; must scope to technology selection only |
| Option 3 (Accepted immediately) | ❌ Invalid | Contains UNKNOWN central claim |

**Board recommendation: Option 1 (Gate 1 first).**
**If the human architect requires faster process: Option 2 is acceptable under the stated condition.**

---

## 7. Cross-ADR Consistency

### 7.1 ADR-001 (Python + asyncio)

| Requirement | Status |
| :--- | :--- |
| Python runtime required | ✅ Procrastinate is a Python library |
| asyncio as I/O model | ✅ Procrastinate is asyncio-native |
| ADR-001 not reopened | ✅ Confirmed |

**No conflicts with ADR-001. Not reopened.**

### 7.2 ADR-002 (PostgreSQL + 7 Invariants)

| ADR-002 Protected Constraint | Gate 1 PASS | Gate 1 FAIL | Status |
| :--- | :---: | :---: | :--- |
| CAS + audit INSERT in one atomic transaction | ✅ | ✅ | Protected in both paths; Outbox pattern preserves atomicity |
| Append-only audit history | ✅ | ✅ | Worker use cases must INSERT, not UPDATE |
| PostgreSQL as persistence layer | ✅ | ✅ | Procrastinate uses PG natively; no additional persistence layer |
| At-least-once external delivery | ✅ | ✅ | ADR-003 explicitly inherits this; no stronger claim made |
| Duplicate publication as accepted residual | ✅ | ✅ | RT-002 zombie window is within this accepted residual |
| Infrastructure-independent domain layer | ✅ | ✅ | Domain layer does not import Procrastinate |

**Gate 1 failure does not threaten any ADR-002 invariant.**

If Gate 1 fails and the Outbox pattern is required, the domain transaction is:

```
CAS UPDATE + audit INSERT + outbox INSERT  [1 PG transaction]
```

The outbox INSERT is in the same domain transaction as the CAS. ADR-002 Invariant 1
(atomic CAS + audit) remains satisfied. The outbox becomes an additional table within
the domain transaction, not an additional service.

**No conflicts with ADR-002 under either Gate 1 outcome. ADR-002 not reopened.**

---

## 8. Decision Options

Presented to the human architect in order of methodological preference:

### Option A — Execute Gate 1, then decide (Recommended)

**Sequence:**

1. Engineering team executes Gate 1 integration test (estimated: 1–2 days).
2. Gate 1 PASS → Human accepts Option A on direct-integration terms → ADR marked ACCEPTED.
3. Gate 1 FAIL → Human accepts Option A on Outbox-pattern terms (or chooses fallback) → ADR marked ACCEPTED.

**Advantages:**

- Human decision is fully informed.
- Accepted ADR contains no UNKNOWN claims.
- The accepted implementation pattern is definitively known.

**Disadvantages:**

- 1–2 days delay before formal acceptance.

---

### Option B — Accept Option A (technology only), validate integration pattern before implementation

**Sequence:**

1. Human accepts "Procrastinate (PostgreSQL-native queue) as the async framework for JincSAE."
2. ADR marked ACCEPTED with explicit clause: "Integration pattern (direct transactional vs. Outbox relay) to be determined by Gate 1 before implementation proceeds."
3. Gate 1 executes; result determines implementation architecture.
4. Implementation specification is produced based on Gate 1 result.

**Advantages:**

- Faster formal acceptance.
- Technology selection is unambiguous and stable.

**Disadvantages:**

- Accepted ADR contains an open implementation pattern question.
- If Gate 1 result changes team's assessment, the ADR may require amendment.

---

### Option C — Accept Option B-TaskIQ immediately (skip Gate 1)

**Rationale for this option:**

If the team prefers to avoid Gate 1 risk entirely and is willing to accept
the recovery scan complexity in exchange for a simpler integration story,
TaskIQ with a recovery scan is a valid architectural choice. It scores 97 vs.
Option A's 109 (or 115 with Gate 1 passing). The 12–18 point gap is significant
but not prohibitive if the team values integration simplicity.

**This option is provided for completeness. The review board does not recommend it.**
The recovery scan implementation complexity is non-trivial (documented in §9.3 of
the Revised Analysis). Trading Gate 1 validation effort for permanent recovery scan
maintenance burden is not a favorable trade.

---

## 9. Minimum Human Decision Package

If the human architect proceeds with **Option A (direct decision on technology)**,
the minimum information they need is:

### 9.1 The Decision Statement

> "Procrastinate (PostgreSQL-native asyncio job queue) is selected as the async
> processing framework for JincSAE. The transactional integration pattern will be
> confirmed by Gate 1 integration testing before implementation proceeds. If Gate 1
> fails, an Outbox relay pattern will be used, maintaining S3 prevention within the
> PostgreSQL ecosystem."

### 9.2 What Is Being Accepted

| Item | Accepted? |
| :--- | :--- |
| Procrastinate as the technology | ✅ YES |
| Direct transactional integration (connection sharing) | ⚠️ PENDING Gate 1 |
| Outbox relay as fallback if Gate 1 fails | ✅ YES (contingent) |
| Zero additional infrastructure services | ✅ YES |
| Procrastinate community/maturity risk | Requires explicit human acceptance |
| 10 Implementation Constraints (IC-001 to IC-010) | ✅ YES (as a package) |
| 7 Architectural Invariants (AI-001 to AI-007, where AI-001 is conditional) | ✅ YES |

### 9.3 What Is NOT Being Accepted

| Item | Status |
| :--- | :--- |
| Exact TTL values (heartbeat, PUBLISHING, scan interval) | DEFERRED to Operations Spec |
| LLM job retry timeout values | DEFERRED to Operations Spec |
| Job retention periods | DEFERRED to Operations Spec |
| Per-queue concurrency limits | DEFERRED to Operations Spec |
| External platform idempotency key strategy | DEFERRED to Publication Infrastructure ADR |
| Recovery scan full implementation specification | DEFERRED to Implementation Spec |
| ORM choice | DEFERRED to Implementation Spec |

### 9.4 Risk Acceptance Summary

Two risks require explicit human acknowledgment:

**Risk 1 — Gate 1 uncertainty:**
> "If Gate 1 fails, the Outbox pattern is required. This adds implementation complexity
> (outbox table + relay logic) but does not change the technology decision."

**Risk 2 — Procrastinate community/maturity:**
> "Procrastinate has a smaller community than Celery or Temporal. If maintenance is
> abandoned, migration to TaskIQ is the documented path. Estimated migration effort:
> 2–3 sprints."

---

## 10. Required Next Step

### If the human architect selects Option A (Execute Gate 1 first)

**Immediate next action:**

> Assign 1–2 engineers to execute Gate 1 integration test using the JincSAE
> PostgreSQL + SQLAlchemy async environment. The test must validate all 6
> cases defined in the Reconciliation §14 Gate 1. Expected duration: 1–2 days.

**After Gate 1 result:**

- **PASS:** Produce `ADR-003-Runtime-and-Queue-Strategy.md` (final ACCEPTED ADR) using MADR format. Reference Gate 1 test result as evidence.
- **FAIL:** Revise the accepted ADR to specify Outbox pattern as the S3 prevention mechanism. Or, if the team reconsiders, evaluate TaskIQ.

---

### If the human architect selects Option B (Accept technology now)

**Immediate next action:**

> Produce `ADR-003-Runtime-and-Queue-Strategy.md` with:
>
> - Status: ACCEPTED
> - Technology: Procrastinate
> - Transactional integration pattern: PENDING GATE 1 (documented explicitly)
> - All invariants except AI-001 as formal
> - AI-001 as a candidate invariant pending validation

**After Gate 1:**

> Amend the accepted ADR with Gate 1 result. AI-001 becomes formal or is replaced
> by the Outbox pattern invariant.

---

### Either path converges to

```
docs/adr/ADR-003-Runtime-and-Queue-Strategy.md  [ACCEPTED]
```

followed by:

```
docs/ops/ADR-003-Operations-Specification.md     [concrete TTL values, timeout values]
docs/impl/ADR-003-Implementation-Specification.md [reference implementation, IC-001 to IC-010]
```

---

## Quality Gate — Self-Assessment

| Check | Status |
| :--- | :--- |
| "5 human decisions" claim independently audited | ✅ Corrected to 2 genuine HDs (HD-1, HD-4) |
| Gate 1 materiality explicitly classified | ✅ §5 — VALIDATES A CENTRAL ARCHITECTURAL PATTERN |
| PASS consequences modeled | ✅ §5.2 |
| FAIL consequences modeled | ✅ §5.3 — ranking unchanged; architecture changes |
| Gate 1 failure changes ranking? Answered explicitly | ✅ NO — Option A remains preferred at 109 vs. 97 |
| Gate 1 failure changes architecture? Answered explicitly | ✅ YES — direct integration vs. Outbox pattern |
| No UNKNOWN central capability silently accepted as fact | ✅ Option 3 (ACCEPTED immediately) explicitly rejected |
| ADR-001 not reopened | ✅ Confirmed |
| ADR-002 not reopened | ✅ Confirmed; all 6 protected invariants verified safe under both Gate 1 outcomes |
| Final verdict is exactly one of three allowed verdicts | ✅ 🟡 READY ONLY AFTER GATE 1 VALIDATION |

---

*This document is the Decision Readiness Review for ADR-003.*
*Verdict: 🟡 `READY ONLY AFTER GATE 1 VALIDATION`*
*The human architect's decision, following Gate 1, produces the final accepted ADR.*
