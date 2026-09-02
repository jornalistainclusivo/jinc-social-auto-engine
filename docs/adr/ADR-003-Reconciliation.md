---
adr-id: ADR-003
artifact-type: Reconciliation / Final Decision Brief
title: "Async Processing, Background Jobs & Workflow Execution — Reconciliation"
status: PROPOSED FOR HUMAN DECISION
date: 2026-09-01
authority-chain:
  - docs/ENGINEERING_CONSTITUTION.md
  - docs/SDD.md
  - docs/adr/ADR-001-Runtime-Language.md
  - docs/adr/ADR-002-Persistence-Strategy.md
reconciles:
  - docs/adr/ADR-003-Analysis.md
  - docs/adr/ADR-003-ArchReview.md
  - docs/adr/ADR-003-Analysis-Revised.md
  - docs/adr/ADR-003-RedTeam.md
produced-by: ADR Reconciliation Board
  roles:
    - architecture-decision-records (Lead — decision integrity, MADR consistency)
    - senior-architect (systemic consistency)
    - database-architect (PostgreSQL transaction semantics)
    - async-python-patterns (Python asyncio / worker runtime)
---

# ADR-003 Reconciliation / Final Decision Brief

# Async Processing, Background Jobs & Workflow Execution

---

## 1. Purpose

This document is the authoritative synthesis of all architectural analysis
performed on ADR-003. Its purpose is not to produce a decision — that belongs to
the human architect. Its purpose is to ensure that the decision is made with a
complete, accurate, and non-contradictory view of the available evidence.

The document is organized as follows:

- **§2–4**: Context and candidate options.
- **§5–6**: Reconciliation of Architecture Review and Red Team findings.
- **§7**: Final evidence classification.
- **§8**: Cross-ADR consistency verification.
- **§9–10**: Corrected decision drivers and revised matrix.
- **§11**: Final option status.
- **§12–13**: Architectural invariants and implementation constraints (separated).
- **§14**: Mandatory validation gates.
- **§15**: Residual risks.
- **§16**: Deferred decisions.
- **§17**: Human decision audit.
- **§18–20**: Final recommendation, decision statement, next steps.

**Status:** `PROPOSED FOR HUMAN DECISION`

This document does not mark ADR-003 as ACCEPTED.

---

## 2. Decision Context

The JincSAE (`jinc-social-engine`) is a Python-based (ADR-001: Accepted) editorial
automation system. Its pipeline produces LLM-generated social media content from
editorial briefs and publishes to external platforms (LinkedIn, Instagram, Twitter/X,
etc.). The pipeline is inherently asynchronous: LLM calls take 5–60 seconds each;
external platform APIs are I/O-bound; content validation requires structured
sequencing; publication scheduling requires future-dated execution.

**The central architectural question:**

> How can a committed domain state transition reliably cause asynchronous downstream work
> without creating an inconsistency between the PostgreSQL domain state and the job queue?

This is the Lost Dispatch Problem (Scenario S3). It is the primary differentiator
between the five candidates evaluated.

**Current preliminary recommendation:** Option A — Procrastinate (PostgreSQL-native queue)

**This recommendation survives reconciliation** under the conditions defined in §18,
with mandatory validation gates in §14 that must be passed before implementation acceptance.

---

## 3. Authoritative Sources

In order of precedence:

| # | Document | Role |
| :--- | :--- | :--- |
| 1 | `docs/ENGINEERING_CONSTITUTION.md` | Absolute constraints |
| 2 | `docs/SDD.md` | System design requirements |
| 3 | `ADR-001-Runtime-Language.md` | Accepted: Python + asyncio |
| 4 | `ADR-002-Persistence-Strategy.md` | Accepted: PostgreSQL + 7 invariants |
| 5 | `ADR-003-Analysis.md` | Original analysis |
| 6 | `ADR-003-ArchReview.md` | Independent architecture review |
| 7 | `ADR-003-Analysis-Revised.md` | Remediated analysis |
| 8 | `ADR-003-RedTeam.md` | Adversarial falsification review |

Where lower-level artifacts (5–8) conflict with accepted documents (1–4), the
authoritative document wins. No conflicts with ADR-001 or ADR-002 were identified
during reconciliation.

---

## 4. Original Recommendation Review

The original analysis (`ADR-003-Analysis.md`) evaluated five candidate options plus
one baseline through 13 decision drivers and an 8-scenario failure mode analysis.

The preliminary recommendation was **Option A — Procrastinate** based primarily on:

1. Ability to enqueue jobs within a PostgreSQL transaction (Driver 3).
2. Zero additional infrastructure services (Driver 1).
3. Native asyncio support (Driver 2).
4. PostgreSQL-durable scheduled execution (Driver 6).

The Architecture Review found the primary claim overstated ("structurally impossible").
The Revised Analysis addressed this. The Red Team found two critical gaps in the
revised claims. This Reconciliation resolves all outstanding findings.

---

## 5. Architecture Review Reconciliation

| Finding | Original Status | Reconciliation Status | Notes |
| :--- | :--- | :--- | :--- |
| **F-001** "Structurally impossible" S3 claim | 🔴 CRITICAL | **RESOLVED** | Language corrected; invariant defined. See §5.1 |
| **F-002** Dual recovery path divergence | 🔴 CRITICAL | **RESOLVED** | Single Recovery Authority Protocol defined. See §5.2 |
| **F-003** Schema migration coupling | 🟠 MAJOR | **RESOLVED** | Alembic `include_name` isolation documented as Implementation Constraint |
| **F-004** PG availability trade-off undeclared | 🟠 MAJOR | **RESOLVED** | Coupled availability explicitly declared and accepted |
| **F-005** Job table maintenance unaddressed | 🟠 MAJOR | **RESOLVED** | Retention policy ownership defined; values deferred to Operations Spec |
| **F-006** Recovery scan complexity understated | 🟠 MAJOR | **RESOLVED** | 5-type retry taxonomy expanded; complexity quantified |
| **F-007** Celery rejected for wrong reason | 🟠 MAJOR | **RESOLVED** | Primary rejection restated as Driver 3 (PG transaction integration) |
| **F-008** Option E threshold undefined | 🟡 MINOR | **RESOLVED** | Failure threshold conditions enumerated |
| **F-009** Temporal dual-authority inconsistency | 🟡 MINOR | **RESOLVED** | Pattern D2 acknowledged; score corrected |
| **F-010** S2 duplicate job observability gap | 🟡 MINOR | **RESOLVED** | Monitoring discipline requirement added |
| **F-011** Driver 9 no discriminating power | 🟡 MINOR | **RESOLVED** | Acknowledged as quality floor, not differentiator |
| **F-012** Concurrent periodic task safety | 🟡 MINOR | **RESOLVED** | Procrastinate `procrastinate_periodic_defers` locking documented |

### 5.1 F-001 Final Disposition

The claim "S3 is structurally impossible" was overstated. The correct formulation,
adopted by this reconciliation:

> S3 (Lost Dispatch) is **preventable** under Option A when the Transactional Dispatch
> Invariant is correctly implemented. It is not prevented by the mere selection of Procrastinate.
> Its prevention requires an integration test (see Gate 1, §14).

**The Transactional Dispatch Invariant (candidate, pending Gate 1 validation):**

> The Procrastinate `defer_async()` call, the CAS UPDATE, and the audit INSERT must
> execute within a single PostgreSQL transaction. The Procrastinate connector must share
> the same database connection as the SQLAlchemy `AsyncSession` in use.
> If this condition is not met, the job INSERT may commit in AUTOCOMMIT mode
> independently of the domain transaction, reproducing the dual-write problem.

**Evidence classification of the invariant's achievability:**
`UNKNOWN / REQUIRES INTEGRATION VALIDATION`

See §6.1 (RT-001 reconciliation) and §14 (Gate 1) for the required validation gate.

### 5.2 F-002 Final Disposition

The Single Recovery Authority Protocol (§8.2 of Revised Analysis) is retained
with precision corrections applied in §6.3 (RT-003 reconciliation).

Final characterization:

> The protocol coordinates two recovery mechanisms (Procrastinate worker lease recovery
> and ADR-002 domain state recovery) through CAS serialization and a TTL ordering safety
> heuristic. It is not exclusive authority by timeout — it is CAS-serialized coordination.
> The TTL ordering is an operational tuning constraint, not a deterministic correctness guarantee.

---

## 6. Red Team Reconciliation

| Finding | Severity | Reconciliation Status | Notes |
| :--- | :--- | :--- | :--- |
| **RT-001** Connection sharing unverified | 🔴 CRITICAL | **REQUIRES VALIDATION GATE** | Gate 1 mandatory before implementation |
| **RT-002** Zombie worker (event loop blocking) | 🔴 CRITICAL | **RESOLVED AS IMPLEMENTATION CONSTRAINT** | Async-only I/O mandatory; does not change decision |
| **RT-003** TTL ordering probabilistic | 🟠 MAJOR | **RESOLVED** — terminology corrected | Recharacterized as safety heuristic |
| **RT-004** SAVEPOINT / begin_nested() anti-pattern | 🟠 MAJOR | **RESOLVED AS IMPLEMENTATION CONSTRAINT** | Explicit prohibition defined |
| **RT-005** Retry timeout vs LLM latency | 🟠 MAJOR | **PARTIALLY RESOLVED** | Architectural requirement defined; exact value deferred |
| **RT-006** CAS 0 rows — silent failure risk | 🟠 MAJOR | **RESOLVED AS IMPLEMENTATION CONSTRAINT** | Repository must raise `StateTransitionRejected` |

---

### 6.1 RT-001 — Connection Sharing: Final Disposition

**Finding recap:** Procrastinate's `defer_async()` participates in the same
PostgreSQL transaction as the SQLAlchemy `AsyncSession` only if both components
share the same underlying database connection. If Procrastinate uses a separate
connection (its own pool, separate asyncpg connection), the job INSERT operates in
AUTOCOMMIT mode and commits independently of the domain transaction. This creates
the dual-write condition regardless of the `session.begin()` boundary.

**Reconciliation Board assessment:**

The Reconciliation Board has reviewed Procrastinate's documented integration patterns
and confirms that connection sharing is NOT automatic:

- Procrastinate's `SQLAlchemyConnector`, when initialized with an SQLAlchemy `Engine`,
  acquires connections from the engine's pool. It does not automatically obtain the
  same connection as the active `AsyncSession`.
- Correct connection sharing requires the Procrastinate connector to be initialized
  or contextually bound to the specific connection held by the current session.
- The exact API for achieving this (e.g., via `App.open_async(pool=session.get_bind())`,
  or via session-level connector injection) depends on the Procrastinate version in use.

**Evidence classification:** `UNKNOWN / REQUIRES INTEGRATION VALIDATION`

The integration pattern is plausible and documented in principle by Procrastinate's
architecture. Whether it works atomically with SQLAlchemy async in the JincSAE stack
is NOT established. It must be verified by Gate 1 before implementation acceptance.

**Decision matrix impact:** Option A's score on Driver 3 (PG Transaction Integration)
carries a conditional quality:

> **Driver 3 Score for Option A: 4 (conditional on Gate 1 validation).**
> If Gate 1 validation demonstrates that connection sharing cannot be achieved
> in the JincSAE stack without introducing unacceptable complexity, the score
> falls to 2, making Option A's advantage on Driver 3 equivalent to Options B–D.
> The human decision must be aware of this conditionality.

**Required validation:** Gate 1 (§14). No integration can proceed on the assumption
that transactional enqueue works until Gate 1 passes.

---

### 6.2 RT-002 — Zombie Worker: Final Disposition

**Finding recap:** In asyncio workers, the heartbeat coroutine runs on the same
event loop as the job function. A blocking synchronous call within a Procrastinate
task function suspends all coroutines, including the heartbeat. Procrastinate's
database-side TTL may then expire, causing the job to be reclaimed while the worker
is alive and executing an external side effect.

**Reconciliation Board assessment:**

This is a **real, Procrastinate-specific failure mode** not present in process-based
workers (Celery prefork). It creates a window during which both the original worker
and a recovery-initiated worker are executing work for the same entity. The domain
consequences are:

1. **Worker lease duplication:** Procrastinate re-queues the job; a new worker picks
   it up. (This is by design — it is the recovery mechanism.)

2. **Domain state duplication:** The new worker attempts the domain CAS transition.
   If the entity is in a state the new worker's CAS does not expect (e.g., entity is
   PUBLISHING but worker's CAS is SCHEDULED→PUBLISHING), the CAS returns 0 rows.
   The new worker exits without changing domain state. **Domain state remains
   consistent.** (ADR-002 CAS invariant holds.)

3. **External side-effect duplication:** If the original worker's blocking call
   completes and the external API responded successfully, the original worker may have
   already dispatched a post to LinkedIn. If the recovery path also results in a
   successful external dispatch (via Worker B or Worker C), two posts may appear on
   the external platform. This is the **ADR-002 formally accepted residual risk**:
   *at-least-once with best-effort deduplication*.

**Critical distinction:**

The zombie worker scenario does NOT introduce new logical categories of risk beyond
what ADR-002 already accepts. It widens the time window during which the residual
risk can materialize. The mitigation (async-only I/O) narrows this window. Neither
the failure mode nor its mitigation changes the category of accepted risk.

**This finding does NOT warrant rejecting Option A.**

**Mandatory implementation constraints derived from RT-002:**

> IC-001: All network I/O operations within Procrastinate task functions
> must use async-compatible libraries. Synchronous blocking calls
> (`requests`, `httpx.Client`, `boto3` blocking calls, etc.) are prohibited
> within async task functions.

> IC-002: Heartbeat interval must be configured to ≤ 1/3 of the Procrastinate
> heartbeat TTL. This provides tolerance for brief event loop pauses without
> triggering false lease expiry.

> IC-003: Procrastinate worker concurrency per process must be bounded to prevent
> a single slow job from monopolizing the event loop and starving heartbeats of
> other in-flight jobs.

These are **Implementation Constraints**, not Architectural Invariants. They do not
change the architecture; they constrain how the architecture is implemented.

---

### 6.3 RT-003 — TTL Ordering: Final Disposition

**Finding recap:** The ordering constraint `PUBLISHING_TTL > Heartbeat_TTL + Scan_Interval`
is subject to PostgreSQL load delays, asyncio timer jitter, and clock skew. It is not
a deterministic guarantee.

**Reconciliation Board assessment:**

The constraint is a **safety heuristic** and **operational tuning parameter**.
It must not be described as exclusive authority or deterministic correctness.

**Precise characterization (replacing §8.2 language of Revised Analysis):**

> **CAS serialization is the correctness mechanism.** The Single Recovery Authority
> Protocol's TTL ordering reduces the probability of concurrent recovery attempts —
> specifically, it reduces the window during which both the Procrastinate lease recovery
> and the ADR-002 PUBLISHING scan are active simultaneously for the same entity.
> Under normal operating conditions, the ordering holds. Under adversarial conditions
> (DB load, clock skew, event loop blocking), the ordering may not hold.
> In all cases, CAS prevents double domain state commitment.
> In all cases, external side-effect duplication remains a residual risk per ADR-002.

**The ordering constraint is operationally required but not architecturally definitive.**
Its concrete values (specific TTL numbers) belong to the Operations Specification, not this ADR.
This ADR defines the relationship: `PUBLISHING_TTL > Heartbeat_TTL + Scan_Interval`.

---

### 6.4 RT-004 — SAVEPOINT Anti-Pattern: Final Disposition

**Finding recap:** `defer_async()` called inside a `session.begin_nested()` (SAVEPOINT)
scope may be rolled back when the SAVEPOINT is rolled back, while the outer transaction
commits — creating S3 (job lost, domain state committed).

**Reconciliation Board assessment:**

This is a real failure mode with a straightforward prevention mechanism.

> **IC-004 (SAVEPOINT Prohibition):** `defer_async()` must not be called inside a
> `session.begin_nested()` context. The defer call must execute at the outermost
> `session.begin()` scope. Violation produces silent S3 (domain state committed, job
> lost). Enforcement: code review gate AND integration test (see Gate 1 scope).

**Permitted transaction boundary:**

```python
async with session.begin():  # CORRECT scope for defer_async()
    await repo.transition_cas(...)  # CAS UPDATE
    await repo.insert_audit(...)  # audit INSERT
    await task.defer_async(...)  # job enqueue — OUTERMOST SCOPE ONLY
    # No begin_nested() between session.begin() and this call.
```

**Prohibited pattern:**

```python
async with session.begin():
    async with session.begin_nested():  # SAVEPOINT
        await task.defer_async(...)  # PROHIBITED HERE — silent S3 on SAVEPOINT ROLLBACK
```

---

### 6.5 RT-005 — Retry Timeout vs. LLM Latency: Final Disposition

**Finding recap:** If the Procrastinate retry timeout for LLM generation jobs is shorter
than the LLM's actual response time, the framework retries the job while the first
attempt is still in-flight. Two LLM calls execute for the same entity. CAS handles
the domain result correctly; two LLM API calls are made (cost and rate-limit concern).

**Reconciliation Board assessment:**

The architectural requirement is:

> **AR-001:** The retry timeout for any job type must exceed the expected execution
> duration for that job type. A retry that fires while the original execution is
> in-flight causes duplicate external calls that cannot be prevented by CAS.

The exact multiplier ("3× P95 LLM latency") is an **operational tuning parameter**
requiring empirical measurement. This ADR does not commit to a specific multiplier.

**Ownership:**

- Architectural requirement (timeout > execution duration): This ADR.
- Exact timeout values: Operations Specification (to be produced before deployment).

---

### 6.6 RT-006 — CAS Zero Rows: Final Disposition

**Finding recap:** When a CAS UPDATE affects zero rows, the application must handle
this explicitly. An implementation that silently treats 0 rows as success will proceed
with external side effects despite the state transition having been rejected, potentially
violating the CAS invariant at the application level.

**Reconciliation Board assessment:**

The CAS mechanism is a database guarantee. The application's obligation is to
check `rows_affected` and respond correctly. This belongs at the **Repository** boundary.

> **IC-005:** The Repository interface for all domain state transitions must raise
> `StateTransitionRejected` (or equivalent) when the CAS UPDATE affects zero rows.
> Task functions must not proceed to external side effects after receiving
> `StateTransitionRejected`. This is a mandatory Repository interface contract.
> **Ownership:** Application domain layer (not infrastructure/queue layer).

The domain layer's state machine is the authority; the Repository enforces the CAS
result; the task function responds to the Repository's signal.

---

## 7. Corrected Evidence Classification

| Claim | Classification | Basis |
| :--- | :--- | :--- |
| "Procrastinate can enqueue within the same PostgreSQL transaction as SQLAlchemy async" | **UNKNOWN / REQUIRES INTEGRATION VALIDATION** | Connection-sharing mechanism plausible but unverified for JincSAE stack |
| "If correctly integrated, the defer INSERT rolls back with the domain transaction" | **SUPPORTED INFERENCE** | PostgreSQL transaction atomicity; IF same connection |
| "Procrastinate periodic tasks deduplicated via `procrastinate_periodic_defers`" | **FACT** | Documented Procrastinate behavior |
| "RQ workers are incompatible with asyncio architecture" | **FACT** | RQ documentation; synchronous worker model |
| "CAS prevents double domain state commitment" | **FACT** | ADR-002 accepted; PostgreSQL UPDATE WHERE semantics |
| "External side-effect duplication is a residual risk" | **FACT** | ADR-002 Decision 2 (accepted) |
| "Blocking I/O within asyncio worker can suspend heartbeat" | **FACT** | Python asyncio single-threaded event loop behavior |
| "PUBLISHING_TTL ordering reduces concurrent recovery window" | **SUPPORTED INFERENCE** | Timer mechanics; subject to load and jitter |
| "Celery cannot participate in PostgreSQL transaction" | **FACT** | Celery architecture; no transactional broker integration |
| "Option A requires zero additional infrastructure beyond PostgreSQL" | **FACT** | Procrastinate deployment requirements |
| "Temporal is disproportionate to MVP workload" | **SUPPORTED INFERENCE** | Temporal deployment complexity vs. PRD workload estimate |
| "Low double-digit articles/day for MVP" | **ASSUMPTION** | PRD does not specify volume |
| "LLM call duration is 5–60 seconds" | **ASSUMPTION** | Typical LLM API latency; not measured for JincSAE |
| "PostgreSQL job table not a bottleneck at MVP scale" | **INFERENCE** | Based on volume assumption; not verified by load test |

---

## 8. Cross-ADR Consistency

### 8.1 ADR-001 Compatibility

| Requirement | Option A Compatibility | Notes |
| :--- | :---: | :--- |
| Python runtime | ✅ | Procrastinate is a Python library |
| asyncio as I/O model | ✅ | Procrastinate is asyncio-native |
| `async def` task functions | ✅ | Standard Procrastinate task definition |
| Dependency management (pip/uv) | ✅ | Standard Python package |
| Testing without external services | ✅ | `InMemoryConnector` for unit tests |
| Observability via Python logging | ✅ | Procrastinate integrates with standard logging |

**No conflicts with ADR-001.**

### 8.2 ADR-002 Compatibility

| ADR-002 Constraint | Option A Compatibility | Notes |
| :--- | :---: | :--- |
| PostgreSQL as persistence layer | ✅ | Procrastinate uses PostgreSQL natively |
| CAS + audit INSERT in one transaction | ✅ (conditional on Gate 1) | Worker use cases must implement Invariant I1 correctly |
| Append-only audit history | ✅ | Worker use cases must not UPDATE audit rows (Repository contract) |
| ContentVersion FK enforced | ✅ | Procrastinate does not touch domain tables |
| Regeneration = new ContentVersion | ✅ | This is a domain use case; queue-independent |
| PublicationAttempt immutable | ✅ | Worker creates new PA on retry; does not UPDATE existing PA status |
| Domain layer has zero infra dependencies | ✅ | Procrastinate confined to infrastructure layer (ADR-002 Invariant 7) |
| At-least-once with best-effort deduplication | ✅ | CAS is the deduplication mechanism; at-least-once is accepted |
| Post-crash duplicate publication is accepted residual risk | ✅ | RT-002 zombie worker scenario is within this accepted risk |

**No conflicts with ADR-002.**

**No accepted invariant is weakened by Option A.**

---

## 9. Corrected Decision Drivers

### 9.1 Corrections Applied

| Driver | Correction Applied |
| :--- | :--- |
| **Driver 3 — PG Transaction Integration** | Option A score is conditional on Gate 1 validation. Score reflects achievability (4), not verification (which is 5). If Gate 1 fails, score drops to 2 — equivalent to Options B–D. |
| **Driver 5 — Retry Semantics** | ARQ score corrected to 2 (no native exponential backoff + jitter; no native dead-letter). |
| **Driver 6 — Delayed/Scheduled Execution** | ARQ score corrected to 3 (Redis sorted set requires `appendfsync always` for full durability; not the default). |
| **Driver 9 — Domain Independence** | Retained as quality floor (all options score 5). Acknowledged as non-differentiating. |

### 9.2 No Double-Counting Detected

The 13 drivers were reviewed for overlap:

- Driver 1 (operational simplicity) vs. Driver 13 (vendor lock-in): distinct — count of services vs. proprietary dependency. **No overlap.**
- Driver 3 (PG transaction integration) vs. Driver 7 (idempotent execution): distinct — enqueue atomicity vs. duplicate delivery safety. **No overlap.**
- Driver 4 (crash recovery) vs. Driver 5 (retry semantics): distinct — job reclaim after worker death vs. configured retry policy. **No overlap.**

No circular reasoning, double-counting, or technology bias detected in driver structure.

---

## 10. Revised Decision Matrix

### 10.1 Scores (Final)

| Driver | Weight | A (Procrastinate) | B-ARQ | B-TaskIQ | C (Celery) | D (Temporal) | E (App-native) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1. Operational Simplicity | 3× | **5** | 4 | 4 | 2 | 2 | **5** |
| 2. Python/asyncio Compat. | 3× | **5** | **5** | **5** | 2 | 4 | **5** |
| 3. PG Tx Integration | 3× | **4*** | 2 | 2 | 2 | 3 | 3 |
| 4. Crash Recovery | 2× | **5** | 4 | 4 | 4 | **5** | 2 |
| 5. Retry Semantics | 2× | **5** | 2 | 4 | **5** | **5** | 1 |
| 6. Delayed/Scheduled Exec | 2× | **5** | 3 | 4 | 4 | **5** | 3 |
| 7. Idempotent Exec Support | 2× | 4 | 3 | 4 | 4 | **5** | 2 |
| 8. Observability | 2× | 4 | 3 | 4 | 4 | **5** | 2 |
| 9. Domain Independence | 2× | **5** | **5** | **5** | **5** | **5** | **5** |
| 10. Dev/Testing Complexity | 1× | 4 | 3 | 3 | 3 | 2 | **5** |
| 11. Scalability | 1× | 4 | 4 | 4 | **5** | **5** | 2 |
| 12. Reversibility | 1× | 4 | 4 | 4 | 3 | 2 | **5** |
| 13. Vendor/Infra Lock-in | 1× | **5** | 3 | 3 | 3 | 2 | **5** |

`* Score 4 is conditional on Gate 1 integration validation. If Gate 1 fails: score 2.`

### 10.2 Weighted Totals (Final)

| Option | Critical (3×) | High (2×) | Medium (1×) | **Total** | **If Gate 1 Fails** |
| :--- | :---: | :---: | :---: | :---: | :---: |
| A — Procrastinate | (5+5+4)×3 = **42** | (5+5+5+4+4+5)×2 = **56** | (4+4+4+5)×1 = **17** | **115** | **109** |
| B — ARQ | (4+5+2)×3 = **33** | (4+2+3+3+3+5)×2 = **40** | (3+4+4+3)×1 = **14** | **87** | **87** |
| B — TaskIQ | (4+5+2)×3 = **33** | (4+4+4+4+4+5)×2 = **50** | (3+4+4+3)×1 = **14** | **97** | **97** |
| C — Celery | (2+2+2)×3 = **18** | (4+5+4+4+4+5)×2 = **52** | (3+5+3+3)×1 = **14** | **84** | **84** |
| D — Temporal | (2+4+3)×3 = **27** | (5+5+5+5+5+5)×2 = **60** | (2+5+2+2)×1 = **11** | **98** | **98** |
| E — App-native | (5+5+3)×3 = **39** | (2+1+3+2+2+5)×2 = **30** | (5+2+5+5)×1 = **17** | **86** | **86** |

**Option A leads at 115. Even if Gate 1 fails (score drops to 109), Option A remains the
highest-scoring candidate.** TaskIQ is the closest alternative at 97.

> **Reconciliation Board note:** The matrix gap between Option A (115/109) and
> Option B-TaskIQ (97) reflects a structural difference, not a marginal preference.
> Option A's leading position is robust to Gate 1 uncertainty because the Driver 3
> advantage of achieving transactional enqueue (even if requiring explicit implementation
> effort) is unique to Option A. The gap between 109 and 97 represents Drivers 1, 2, 5,
> 6, 13 — all of which are unaffected by Gate 1.

---

## 11. Candidate Options — Final Status

| Option | Status | Primary Basis |
| :--- | :--- | :--- |
| **A — Procrastinate** | **RECOMMENDED** (conditional on Gate 1) | Only candidate offering transactional job enqueue; no additional services; native asyncio; PostgreSQL-durable scheduling |
| **B — TaskIQ** | **VIABLE BUT NOT PREFERRED** | Best non-PG-native alternative; native asyncio; configurable retries; requires Redis (+1 service); S3 requires recovery scan |
| **B — ARQ** | **VIABLE BUT NOT PREFERRED** | Native asyncio; but no built-in dead-letter (Constitution §15 tension), no native exponential backoff, Redis durability configuration required for scheduled jobs |
| **C — Celery** | **REJECTED FOR MVP** | Primary: cannot participate in PostgreSQL transactions (Driver 3); Secondary: 2–4 additional services disproportionate to MVP workload; asyncio compatibility incomplete |
| **D — Temporal** | **REJECTED FOR MVP** | 2–3 additional infrastructure services; programming model complexity disproportionate to JincSAE pipeline; dual-authority concern resolvable but requires significant architectural discipline not justified by PRD scope |
| **B — RQ** | **ELIMINATED** | Synchronous worker model incompatible with asyncio (ADR-001) |
| **E — App-native** | **REJECTED AS PRIMARY STRATEGY** | No built-in retry, no dead-letter, no crash recovery between process restarts; valid for prototype-only phase |

**Fallback option if Gate 1 fails:**

If Gate 1 demonstrates that Procrastinate + SQLAlchemy async connection sharing is not
achievable in the JincSAE stack without unacceptable complexity, the fallback is
**Option B — TaskIQ** with a recovery scan (the S3 recovery scan complexity is documented
in §9.3 of the Revised Analysis). The fallback changes the architecture; it does not change
the decision to use PostgreSQL as the persistence layer (ADR-002).

---

## 12. Final Architectural Invariants

These are architectural invariants — they constrain the shape of the architecture,
not the implementation details.

### AI-001 — Transactional Dispatch Invariant (Candidate — pending Gate 1 validation)

> A domain state transition that requires asynchronous downstream execution must not
> commit without its corresponding job being registered in the same PostgreSQL transaction.
> The `defer_async()` call must execute within the same transaction boundary as the CAS
> UPDATE and audit INSERT. Separate connections produce separate transaction lifecycles
> regardless of framework selection.

**Status:** Candidate invariant. Achievability requires Gate 1 validation. Becomes
a formal invariant upon Gate 1 passage.

### AI-002 — CAS Guard Invariant (Inherited from ADR-002)

> Every domain state transition executed by a worker must use the CAS mechanism defined
> in ADR-002. No worker may write a domain state without a `WHERE status = 'EXPECTED_STATE'`
> guard. A CAS result of zero rows must terminate the use case execution without external
> side effects.

**Status:** Formal invariant. Inherited from ADR-002 Invariant 1. Binding on all workers
regardless of option chosen.

### AI-003 — Audit Append-Only Invariant (Inherited from ADR-002)

> Workers must not UPDATE existing audit records. Worker use cases must INSERT new
> `content_version_transitions` rows for each state change. Failed or rolled-back
> transitions must not produce partial audit records.

**Status:** Formal invariant. Inherited from ADR-002 Invariant 2.

### AI-004 — Domain Layer Infrastructure Independence (Inherited from ADR-002)

> The domain layer must have zero direct dependencies on the queue infrastructure.
> Procrastinate task definitions and dispatcher calls must be confined to the infrastructure
> layer. Domain use cases must not import from Procrastinate.

**Status:** Formal invariant. Inherited from ADR-002 Invariant 7.

### AI-005 — Single Recovery Authority Protocol (Candidate — operationally tuned)

> Worker lease recovery (Procrastinate heartbeat) and domain state recovery
> (ADR-002 PUBLISHING scan) must not independently re-dispatch the same business
> operation without CAS-based serialization. The TTL ordering constraint
> `PUBLISHING_TTL > Worker_Heartbeat_TTL + Recovery_Scan_Interval` must be
> maintained as a safety heuristic. CAS is the definitive correctness mechanism;
> TTL ordering is an operational parameter reducing concurrent recovery probability.

**Status:** Candidate invariant. Concrete TTL values deferred to Operations Specification.

### AI-006 — Retry Timeout Budget Invariant

> The Procrastinate retry timeout for any task type must exceed the expected
> maximum execution duration for that task type. A retry that fires while the
> original execution is in-flight causes duplicate external I/O that cannot
> be prevented by CAS.

**Status:** Architectural requirement. Concrete values deferred to Operations Specification.

### AI-007 — At-Least-Once External Dispatch (Inherited from ADR-002)

> External publication semantics are at-least-once with best-effort deduplication.
> Exactly-once external dispatch is not claimed by ADR-003 for any option. The residual
> risk of duplicate external publication (post-crash or post-partition) is accepted
> per ADR-002 Decision 2.

**Status:** Formal invariant. Inherited from ADR-002.

---

## 13. Mandatory Implementation Constraints

These are implementation constraints — they constrain HOW the architecture is
implemented, not its shape. They do not belong in the ADR's invariant section.
They belong in the Implementation Specification produced after ADR acceptance.

| ID | Constraint | Owner | Enforcement |
| :--- | :--- | :--- | :--- |
| **IC-001** | All network I/O within Procrastinate task functions must use async-compatible libraries. Synchronous blocking calls (`requests`, `httpx.Client`, etc.) are prohibited within `async def` task functions. | Application / Worker | Code review; Gate 3 test |
| **IC-002** | Heartbeat interval must be configured to ≤ 1/3 of the Procrastinate heartbeat TTL. | DevOps / Config | Deployment configuration gate |
| **IC-003** | Procrastinate worker concurrency per process must be bounded to prevent event loop starvation. | DevOps / Config | Deployment configuration gate |
| **IC-004** | `defer_async()` must not be called inside `session.begin_nested()` (SAVEPOINT). Defer must execute at the outermost `session.begin()` scope. | Application / Worker | Code review; Gate 1 scope |
| **IC-005** | Repository state transition methods must raise `StateTransitionRejected` (or equivalent) when CAS UPDATE `rowcount == 0`. Task functions must not proceed to external side effects after `StateTransitionRejected`. | Application / Domain | Unit test per transition |
| **IC-006** | Procrastinate tables must be excluded from Alembic `autogenerate` via `include_name` callback in `env.py`. Procrastinate schema updates must use `procrastinate schema apply` independently of domain migrations. | Infrastructure / DevOps | Migration CI gate |
| **IC-007** | LLM generation job retry timeout must exceed P95 LLM response latency. Exact value to be determined in Operations Specification. | Operations Spec | Pre-deployment validation |
| **IC-008** | Completed and failed Procrastinate jobs must be pruned on a defined schedule. Retention policy: succeeded jobs 30 days; failed jobs 90 days (values to be confirmed in Operations Specification). | DevOps | Operational runbook |
| **IC-009** | `StateTransitionRejected` exits must be monitored and distinguished from genuine failures in observability tooling. CAS-rejected idempotent exits must not trigger failure alerts. | Observability | Monitoring configuration |
| **IC-010** | Rolling deployments that include Procrastinate version upgrades must verify schema backward compatibility before deploying new application version. | DevOps | Deployment checklist |

---

## 14. Required Validation Gates

These gates are mandatory. Implementation may not proceed on the basis of assumed
correctness. Each gate must produce evidence — not argument.

---

### Gate 1 — Transactional Enqueue Integration Test

**Purpose:** Verify that Procrastinate `defer_async()` participates in the same
PostgreSQL transaction as the SQLAlchemy `AsyncSession` in the JincSAE stack, such
that the job INSERT rolls back with the domain transaction.

**Scope:** Must test:

1. Domain CAS UPDATE + audit INSERT + `defer_async()` within `session.begin()`.
2. Artificial failure after `defer_async()` but before session commit.
3. Verify: job does NOT appear in `procrastinate_jobs` after rollback.
4. Verify: domain entity state is unchanged after rollback.
5. Positive case: successful transaction results in job appearing in `procrastinate_jobs`.
6. Negative case (SAVEPOINT prohibition): `defer_async()` inside `session.begin_nested()`, SAVEPOINT rolled back, outer transaction committed — verify job does NOT exist.

**Constraints:**

- Must use real PostgreSQL. No in-memory mock may prove transactional correctness.
- Must use the actual JincSAE SQLAlchemy async configuration.
- Must use the actual Procrastinate connector configuration to be used in production.

**Gate pass criteria:**

- All 6 test cases pass.
- The exact connection-sharing API pattern is documented as a reference implementation.

**If Gate 1 fails:**

- The Transactional Dispatch Invariant (AI-001) is not achievable with the current stack.
- ADR-003 must be revised: Option A's Driver 3 advantage disappears.
- Fallback to Option B-TaskIQ must be formally evaluated.
- Human decision deferred pending Gate 1 resolution.

---

### Gate 2 — Worker Crash / Lease Recovery

**Purpose:** Verify that domain state cannot be committed twice under concurrent
worker execution following a lease reclaim.

**Scope:** Must test:

1. Worker A starts a job; simulated crash (process kill).
2. Procrastinate heartbeat TTL expires; job re-queued.
3. Worker B picks up the re-queued job.
4. Verify: CAS prevents Worker B from committing the same state transition twice.
5. Worker A resurrection (simulated): Worker A resumes with the original job context.
6. Verify: CAS prevents Worker A from committing if Worker B already succeeded.
7. Verify: Only one `content_version_transitions` row exists for the transition.

**Gate pass criteria:** All 7 assertions pass. Domain state is consistent under all tested crash/recovery sequences.

---

### Gate 3 — Blocking I/O Detection and Prevention

**Purpose:** Verify that asyncio event loop blocking is detectable and preventable in CI.

**Scope:**

1. Introduce a deliberate `time.sleep(5)` inside a Procrastinate task function.
2. Verify that Procrastinate's heartbeat is delayed during the sleep.
3. Verify that the CI environment has a linter/detector for blocking calls in async functions
   (e.g., `asyncio-mode` + `anyio` + `flake8-async` or equivalent).
4. Positive case: `httpx.AsyncClient` in task function → heartbeat not delayed.

**Gate pass criteria:**

- Blocking call detection in CI prevents merge of code with synchronous I/O in async task functions.
- OR: Team commits to alternative enforcement mechanism (e.g., mandatory async-only SDK contracts in code review).

---

### Gate 4 — Publication Residual Risk Characterization

**Purpose:** Confirm that ADR-003 does not introduce stronger guarantees than ADR-002 accepts.

**Scope:**

1. Document the window during which duplicate external dispatch is possible under Option A.
2. Verify this window is not wider than what a Redis-backed alternative would produce.
3. Explicitly verify that no code path claims `exactly_once_publication = True`.

**Gate pass criteria:** Window is characterized; it is consistent with ADR-002's
accepted at-least-once semantics. No component claims exactly-once publication.

---

## 15. Residual Risks

| Risk | Category | Severity | Mitigation | Residual After Mitigation |
| :--- | :--- | :---: | :--- | :--- |
| Gate 1 fails — connection sharing not achievable | Architectural | HIGH | Gate 1 mandatory before implementation | Fallback to TaskIQ if Gate 1 fails |
| Zombie worker (event loop blocking) | Implementation | MEDIUM | IC-001, IC-002, IC-003; Gate 3 | Narrow window; at-least-once accepted per ADR-002 |
| SAVEPOINT anti-pattern | Implementation | MEDIUM | IC-004; code review gate | Eliminated if IC-004 enforced |
| LLM retry overlap (duplicate LLM calls) | Operational | LOW | IC-007 (timeout > P95 latency) | Cost concern; not correctness failure |
| Job table growth and VACUUM pressure | Operational | LOW (MVP) | IC-008 (pruning policy) | Acceptable at MVP scale |
| Procrastinate library abandonment | Strategic | LOW | Migration path to TaskIQ documented | Medium migration effort; 2–3 sprints |
| PG outage recovery burst | Operational | LOW (MVP) | Per-queue concurrency limits | Bounded by Procrastinate configuration |
| Mixed-version rolling deployment | Operational | MEDIUM | IC-010 (Procrastinate schema compat check) | Managed by deployment checklist |
| Duplicate external publication | Inherent residual | ACCEPTED | Best-effort deduplication via external_id + CAS | Accepted per ADR-002 Decision 2 |
| CAS 0-rows silent failure | Implementation | MEDIUM | IC-005 (StateTransitionRejected) | Eliminated if IC-005 enforced |

---

## 16. Deferred Decisions

The following items are explicitly deferred. They are NOT part of this ADR.

| Deferred Item | Reason for Deferral | Owner |
| :--- | :--- | :--- |
| Exact Procrastinate heartbeat TTL values | Operational parameter; depends on deployment environment and external API SLAs | Operations Specification |
| Exact PUBLISHING_TTL value | Same as above | Operations Specification |
| LLM job retry timeout exact value | Requires P95 latency measurement in production | Operations Specification |
| Job retention values (30 days succeeded / 90 days failed) | Suggested; not binding | Operations Specification |
| External platform idempotency key strategy (LinkedIn, Instagram, etc.) | Provider-specific API concern | Publication Infrastructure ADR |
| Per-queue Procrastinate concurrency limits | Deployment-time configuration | Operations Specification |
| ORM choice (SQLAlchemy Core vs. ORM) | Not an ADR-003 concern | Implementation Specification |
| Authentication and authorization | Not an ADR-003 concern | Security ADR |
| Recovery scan implementation (full specification) | Design concern post-ADR | Implementation Specification |

---

## 17. Human Decision Audit

### 17.1 TRUE HUMAN DECISIONS

These are the decisions that genuinely require human judgment. They cannot be derived
from the Engineering Constitution, SDD, or accepted ADRs.

| # | Decision | Context |
| :--- | :--- | :--- |
| **HD-1** | Accept Option A (Procrastinate) as the primary queue strategy, conditional on Gate 1 validation | Core strategic choice; non-trivial reversal cost after implementation begins |
| **HD-2** | Accept the coupled-availability trade-off (PostgreSQL outage = queue outage) | Business risk tolerance; acceptable at MVP given that all JincSAE operations require PG |
| **HD-3** | Proceed to Gate 1 immediately, or defer ADR-003 until Gate 1 is complete | Sequencing decision; Gate 1 requires a working PostgreSQL + SQLAlchemy async environment |
| **HD-4** | Accept Procrastinate's community/maturity risk | Smaller ecosystem than Celery; if abandoned, medium migration effort to TaskIQ |
| **HD-5** | If Gate 1 fails: accept Option B-TaskIQ as fallback (requires Redis, recovery scan implementation) | Contingency decision |

### 17.2 ARCHITECTURAL CONSEQUENCES (Not Human Decisions)

These items are consequences of the decisions above, not independent choices:

- Procrastinate tables in PostgreSQL (consequence of HD-1)
- Alembic exclusion of Procrastinate tables (consequence of HD-1 + IC-006)
- Worker process architecture (asyncio, single worker type) (consequence of ADR-001 + HD-1)
- Job table pruning requirement (consequence of HD-1)
- Recovery scan for PUBLISHING TTL (consequence of ADR-002)
- `StateTransitionRejected` in Repository (consequence of CAS + IC-005)

### 17.3 VALIDATION GATES (Not Human Decisions)

Gate 1 through Gate 4 are not human decisions. They are technical validation requirements.
The human decides whether to proceed before Gate 1 (HD-3). Gate 1 itself is engineering work.

### 17.4 DEFERRED DOWNSTREAM DECISIONS (Not Part of This ADR)

See §16. All operational parameters (TTL values, retry timeouts, retention periods)
are deferred to the Operations Specification and do not require a human decision here.

---

## 18. Final Recommendation

### Recommended: Option A — Procrastinate (PostgreSQL-Native Queue)

**Conditional on Gate 1 (Transactional Enqueue Integration Test) passing.**

**Primary basis for recommendation:**

Option A is the only candidate offering the structural capability to prevent Scenario S3
(Lost Dispatch) by registering jobs within the same PostgreSQL transaction as the domain
state change. This capability:

1. Directly addresses the project's most critical architectural failure mode.
2. Does not require additional infrastructure beyond what ADR-002 has already mandated.
3. Is consistent with ADR-001 (Python asyncio) and ADR-002 (PostgreSQL + 7 invariants).
4. Provides the strongest scheduler durability (jobs are PostgreSQL rows).
5. Does not introduce vendor lock-in beyond the PostgreSQL commitment already made.

**Caveat:** S3 prevention is achievable by correct implementation, not automatic by
library selection. The Transactional Dispatch Invariant (AI-001) must be validated
by Gate 1. If Gate 1 fails, Option B-TaskIQ is the fallback — which reduces S3
prevention to recovery scan (compensating, not structural).

**Option A leads the revised decision matrix at 115 (or 109 if Gate 1 fails).
Even under the pessimistic Gate 1 failure scenario, Option A remains the highest-scoring
candidate, making the decision robust.**

**Claims NOT made by this recommendation:**

- Exactly-once external publication ❌ (ADR-002 accepted residual applies)
- Automatic S3 elimination by mere library selection ❌ (Gate 1 required)
- Deterministic recovery-race prevention by TTL ordering ❌ (CAS is the correctness mechanism)
- Zero operational burden from PostgreSQL-backed jobs ❌ (pruning and Alembic isolation required)

---

## 19. Decision Required

The human architect is presented with the following consolidated decision:

### Decision Statement

> **ADR-003: Async Processing, Background Jobs & Workflow Execution**
>
> Having reviewed the five candidate options and their complete evidence chain
> (analysis, architecture review, remediation, Red Team), the Reconciliation Board
> recommends:
>
> **Option A — Procrastinate (PostgreSQL-Native Queue)**
>
> as the primary asynchronous job engine for the JincSAE pipeline, subject to:
>
> 1. **Gate 1 passage** — Integration test confirming Procrastinate + SQLAlchemy async
>    transactional enqueue in the JincSAE stack.
> 2. **Acceptance of mandatory implementation constraints** IC-001 through IC-010.
> 3. **Acceptance of the coupled-availability trade-off** (PostgreSQL outage = queue outage).
> 4. **Acceptance of Procrastinate's community/maturity profile** with the documented
>    migration path (→ TaskIQ) if the library is abandoned.

### Options Available to the Human Architect

| Option | Effect |
| :--- | :--- |
| **Accept Option A** (pending Gate 1) | Proceed to Gate 1 validation; if passes, proceed to final ADR |
| **Accept Option A unconditionally** | Accept the transactional enqueue claim as adequate inference; proceed to final ADR with documentation of integration requirement |
| **Defer until Gate 1 complete** | Conduct Gate 1 first; make decision based on result |
| **Accept Option B-TaskIQ as fallback immediately** | Skip Gate 1; accept S3 recovery scan complexity; proceed with Redis (+1 service) |
| **Reject all options — reopen analysis** | If human has evidence that no candidate satisfies the requirements; requires new analysis scope |

---

## 20. Next Steps

If the human decision is:

**A — "Accept Option A (pending Gate 1)":**

1. Engineering team executes Gate 1 integration test.
2. If Gate 1 passes: produce `ADR-003-Runtime-and-Queue-Strategy.md` (final accepted ADR) using MADR format.
3. If Gate 1 fails: report findings; evaluate fallback (Option B-TaskIQ); human decides on fallback.
4. Produce Operations Specification document with concrete TTL values, retention periods, and retry timeouts.
5. Produce Implementation Specification with reference implementation for Transactional Dispatch Invariant.

**B — "Accept Option A unconditionally":**

1. Produce `ADR-003-Runtime-and-Queue-Strategy.md` immediately.
2. Flag Gate 1 as a required pre-deploy validation in the ADR body.
3. Proceed to Operations Specification and Implementation Specification.

**C — "Accept Option B-TaskIQ as fallback":**

1. Produce supplementary analysis comparing Option A (Gate 1 failed) vs. Option B-TaskIQ.
2. Human makes final decision.
3. Produce final ADR for accepted option.

**The next artifact, if Option A is accepted, is:**

```
docs/adr/ADR-003-Runtime-and-Queue-Strategy.md
```

Status: `ACCEPTED`
Format: MADR (same as ADR-001, ADR-002)

---

## Final Quality Gate — Self-Assessment

| Check | Status |
| :--- | :--- |
| RT-001 reconciled: transactional enqueue classified as UNKNOWN/REQUIRES VALIDATION | ✅ §6.1 |
| RT-002 reconciled: zombie worker as implementation constraint, not decision changer | ✅ §6.2 |
| RT-003 reconciled: TTL ordering as safety heuristic, not deterministic guarantee | ✅ §6.3 |
| RT-004 reconciled: SAVEPOINT prohibition as IC-004 | ✅ §6.4 |
| RT-005 reconciled: architectural requirement vs. operational parameter separated | ✅ §6.5 |
| RT-006 reconciled: StateTransitionRejected as Repository contract | ✅ §6.6 |
| F-001 through F-007 all reconciled with final status | ✅ §5 |
| Transactional enqueue NOT claimed as proven without integration evidence | ✅ §6.1, §7, §14 Gate 1 |
| Exactly-once semantics NOT claimed | ✅ AI-007, §18 |
| Worker lease duplication ≠ domain state duplication ≠ external side-effect duplication | ✅ §6.2 |
| External side-effect duplication aligned with ADR-002 Decision 2 | ✅ AI-007, §8.2 |
| Architectural invariants separated from implementation constraints | ✅ §12 vs. §13 |
| Human decisions separated from consequences and validation gates | ✅ §17 |
| ADR-001 not contradicted | ✅ §8.1 |
| ADR-002 not contradicted | ✅ §8.2 |
| Status is PROPOSED FOR HUMAN DECISION | ✅ Document header |

---

*This document is the Reconciliation / Final Decision Brief for ADR-003.*
*Status: `PROPOSED FOR HUMAN DECISION`*
*The human architect's decision converts this document into the accepted ADR.*
