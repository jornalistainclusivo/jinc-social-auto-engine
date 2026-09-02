# ADR-003 Architecture Review Report

**Status:** Independent Architecture Review — Do Not Modify ADR-003-Analysis.md Based on This Report Alone  
**Artifact Reviewed:** `docs/adr/ADR-003-Analysis.md`  
**Review Date:** 2026-08-31  
**Authority Hierarchy:** Engineering Constitution > PRD > SDD > ADR-001 > ADR-002 > ADR-003-Analysis  
**Reviewer posture:** Adversarial and independent. Every claim treated as unproven until grounded in evidence.

---

## Executive Verdict: CONDITIONAL

The ADR-003 Analysis is directionally sound. The preliminary recommendation of Procrastinate (Option A) is defensible, but **five of its supporting claims are materially overstated or unverified**, and **two structural failure modes are absent from the analysis**. These gaps would create false confidence if the ADR is accepted without correction.

The analysis is not ready for human decision in its current form. It requires targeted revision on the specific findings below before proceeding to Red Team or Reconciliation.

No new technology is introduced. No decision is made by this review.

---

## 1. Critical Findings

### FINDING-001 (CRITICAL) — "Structurally Impossible" Is an Overstated Claim

**Location:** §8 Transaction/Queue Consistency Analysis; §5 Option A description

**Claim reviewed:**
> "There is no dual-write problem. S3 is **structurally impossible**."

**Finding:** This claim is too strong and partially false.

Procrastinate's transactional enqueue capability is real. However, "structurally impossible" implies that the architecture itself prevents S3 regardless of implementation. This is incorrect. S3 remains possible under Procrastinate if:

1. The developer calls `task.defer_async()` **outside** the SQLAlchemy `session.begin()` block — either by mistake or due to a code path that catches an exception before the defer call.
2. The Procrastinate async connector uses a **different database connection** than the SQLAlchemy session. In SQLAlchemy async, the connection is tied to the session context; Procrastinate must be explicitly configured to share it. Misconfiguration produces a separate transaction that does not roll back with the domain transaction.
3. A future developer adds a `session.commit()` mid-use-case (pre-commit pattern) before the defer, breaking the atomicity assumption.

**Evidence:** Procrastinate documentation explicitly requires careful integration with SQLAlchemy to share the same connection. The `SyncPgConnector` and async equivalents must be instantiated with or adapted to the existing connection. This is a documented integration requirement, not an automatic guarantee. (FACT — Procrastinate integration docs)

**Correction required:** Replace "structurally impossible" with "achievable through correct transactional integration, which requires explicit implementation discipline at the Repository/Use Case boundary." The analysis should specify the invariant: *"The Procrastinate defer call must execute within the same `session.begin()` context as the CAS UPDATE and audit INSERT."* This is an application-level invariant, not a Procrastinate guarantee.

**Impact:** This is the single most important claim in the analysis. If it is overstated, the primary justification for Option A's score of 5 on Driver 3 (PG Transaction Integration) is weakened. The score remains defensible but must be qualified.

---

### FINDING-002 (CRITICAL) — Missing Failure Mode: Dual Recovery Path Divergence

**Location:** §7 Failure-Mode Analysis, Scenario S1; §12 Operational Analysis

**Missing scenario:** The analysis describes S1 (worker crash) as resolved by "Procrastinate heartbeat TTL → job reclaimed." This is incomplete. There is a **dual recovery path divergence** not addressed anywhere in the analysis.

**The gap:**

When a Procrastinate worker claims a job (job status → `doing`) and begins executing a use case, the use case may perform a domain state transition (e.g., CAS: `SCHEDULED → PUBLISHING`) before the external call. The worker then crashes.

The system now has **two independent stale states**:

1. The Procrastinate job table: `status = 'doing'` — recoverable by the Procrastinate heartbeat TTL mechanism.
2. The PostgreSQL domain table: `content_versions.status = 'PUBLISHING'` — recoverable only by the ADR-002 PUBLISHING TTL recovery scan.

These are **two separate recovery mechanisms** on **two separate timers** that may fire in different orders:

- If the Procrastinate heartbeat TTL fires first → the job is requeued as `queued` → a new worker picks it up → CAS on `PUBLISHING → PUBLISHING` returns 0 rows (entity is already PUBLISHING) → the worker exits gracefully BUT the entity is stuck in PUBLISHING indefinitely until the ADR-002 recovery scan fires.
- If the ADR-002 PUBLISHING scan fires first → it resets PUBLISHING to SCHEDULED and creates a new PublicationAttempt → but now both the original (stale) Procrastinate job AND a new recovery-dispatched job are competing for the same entity.

**This is a concurrency hazard specific to Procrastinate's crash recovery interacting with ADR-002's PUBLISHING recovery protocol.** The analysis does not model this interaction.

**Correction required:** The analysis must define the relationship between the Procrastinate heartbeat TTL and the ADR-002 PUBLISHING TTL. At minimum: the PUBLISHING TTL must be longer than the Procrastinate heartbeat timeout + one polling interval, to ensure the Procrastinate recovery mechanism fires first. This ordering relationship must be specified as an architectural invariant.

---

## 2. Major Findings

### FINDING-003 (MAJOR) — Schema Migration Coupling Not Addressed

**Location:** §12 Operational Analysis; §5 Option A description

**Claim reviewed:**
> "Schema impact: adds approximately 3–4 tables to the PostgreSQL schema."

**Finding:** The analysis treats this as a low-cost observation. It fails to address a material operational consequence: Procrastinate's job tables and the application's domain tables now share the same Alembic migration history.

**Consequences:**

- A Procrastinate version upgrade that adds or modifies job table columns requires coordinating with the domain schema migration sequence. A Procrastinate upgrade may require a migration that conflicts with or depends on a domain migration.
- If Procrastinate tables are included in Alembic's `autogenerate`, any Procrastinate schema change (including upstream library changes) will appear in the project's `alembic revision --autogenerate` output, polluting the domain migration history.
- To isolate this, Procrastinate must be configured to exclude its tables from Alembic autogenerate (via `include_schemas` or `include_name` filtering). This is a configuration requirement that must be documented and enforced.

**Correction required:** The analysis must acknowledge this schema coupling concern and specify the mitigation: Procrastinate tables must be excluded from Alembic autogenerate via explicit include/exclude configuration, or managed via a separate migration namespace.

---

### FINDING-004 (MAJOR) — PostgreSQL Unavailability Creates Full System Unavailability Under Option A

**Location:** §12 Operational Analysis; §6.2 Infrastructure Services Required; Decision Matrix Driver 11 (Scalability)

**Claim reviewed (implicit):** Option A is scored 5 on Operational Simplicity because it requires zero additional infrastructure services. This conflates "fewer services" with "better availability."

**Finding:** Under Options B/C/D, if PostgreSQL becomes temporarily unavailable:

- The job queue (Redis) remains operational.
- Workers that do not require a DB write can continue processing non-blocking jobs.
- New jobs can be enqueued by the API while PG is recovering.

Under Option A (Procrastinate), if PostgreSQL becomes temporarily unavailable:

- The job queue is unavailable.
- Worker discovery of new jobs is unavailable.
- The API cannot enqueue new jobs.
- The entire async pipeline halts.

**For the JincSAE MVP and its stated reliability requirements, this is an acceptable trade-off** — PostgreSQL downtime also means the domain state is unavailable, so pipeline halting is expected. However, the analysis does not acknowledge this trade-off, which means the human decision-maker is not informed of it.

**Correction required:** The analysis should explicitly note that Option A's "zero additional services" comes with a coupled availability property: queue and database availability are identical. Redis-backed options decouple queue availability from database availability. For the JincSAE MVP workload and team size, this trade-off is likely acceptable, but it must be stated, not omitted.

---

### FINDING-005 (MAJOR) — Procrastinate Job Table Maintenance Not Addressed

**Location:** §5 Option A; §12 Operational Analysis

**Finding:** Failed and completed Procrastinate jobs accumulate in the `procrastinate_jobs` table indefinitely unless explicitly pruned. At low-to-moderate volume, this is not a performance problem. However:

1. The `procrastinate_events` table (job history) grows unboundedly without a pruning policy.
2. PostgreSQL table bloat and index bloat on the job table will eventually affect query performance.
3. VACUUM behavior on a frequently-updated job table may need tuning.

The analysis presents Option A's schema addition as a minor concern. It does not address the operational requirement for job table maintenance (pruning, archiving, or TTL on completed jobs).

**This is an operational requirement specific to Option A that does not apply to stateless Redis-backed queues** (where completed jobs are automatically evicted from Redis).

**Correction required:** The analysis must acknowledge that Procrastinate requires a periodic job table cleanup policy. This is a minor operational burden but must be documented.

---

### FINDING-006 (MAJOR) — Scenario S3 Recovery Scan for Options B/C/D Is Understated

**Location:** §7 Failure-Mode Analysis, Scenario S3; §8 Transaction/Queue Consistency Analysis

**Claim reviewed:**
> "Maximum stall time = polling interval. A periodic recovery scan... detects stalled entities."

**Finding:** The analysis correctly identifies that Options B/C/D require a recovery scan. However, it understates the implementation complexity of this scan. A correct recovery scan for the JincSAE pipeline must:

1. **Distinguish legitimate intermediate states from stuck states.** A ContentVersion in `VALIDATED` status may be legitimately awaiting a queue job that is queued but not yet started. The scan must not re-enqueue if a job is already in-flight.
2. **Prevent the scan from creating duplicate jobs.** If the scan runs and enqueues a recovery job while the original job is still in-flight (delayed by queue saturation), two workers will attempt the same state transition. The CAS guard handles this at the domain level, but the queue will have two orphaned jobs — one that succeeded and one that will permanently fail.
3. **Require per-state scan logic.** A `VALIDATED` entity needs a different recovery action than a `SCHEDULED` entity. The scan is not a single query but a multi-state policy.

The analysis presents the recovery scan as a simple compensating mechanism. A correct implementation is non-trivial and represents a meaningful development cost for Options B/C/D.

**Correction required:** The analysis should quantify the recovery scan as a non-trivial implementation that must be designed, tested, and maintained. It is not equivalent to "a few SQL queries." This affects the scoring of Driver 10 (Development & Testing Complexity) for Options B/C/D.

---

### FINDING-007 (MAJOR) — Celery Elimination Is Correct but Evidence Is Partially Stale

**Location:** §5 Option C; §6.3 asyncio Compatibility

**Claim reviewed:**
> "Celery 5.x has begun adding asyncio support, but it is not fully production-stable as of the analysis period."

**Finding:** The claim is directionally correct — Celery's asyncio support has historically been incomplete. However, "as of the analysis period" is vague. Celery 5.4+ introduced more complete asyncio support via `asyncio` worker class. The claim should be more precise about what is verified vs. assumed.

**More importantly:** The analysis dismisses Celery primarily on asyncio grounds. But even if Celery's asyncio support were complete, Celery's score on Driver 3 (PG Transaction Integration) would remain 2, because Celery cannot enqueue within a PostgreSQL transaction. This is the more architecturally relevant reason for rejection — and it applies regardless of asyncio support status.

**Correction required:** Clarify that Celery's rejection is primarily on Driver 3 (PG transaction integration), not solely on asyncio compatibility. The asyncio concern is secondary and should be labeled INFERENCE rather than FACT pending version-specific verification.

---

## 3. Minor Findings

### FINDING-008 (MINOR) — Option E "Production Inadequacy" Lacks a Threshold

**Location:** §5 Option E; §18 Preliminary Recommendation

**Claim reviewed:**
> "Option E is unsuitable for production."

**Finding:** "Production inadequacy" is asserted without defining the failure threshold. The PRD does not specify article volume. At truly minimal scale (fewer than 10 articles/day, single editor), Option E may be operationally viable for a prototype phase, with a documented upgrade trigger (e.g., "when article volume exceeds N/day or when a publication failure is undetectable within M minutes").

The binary "unsuitable for production" label prevents the analysis from acknowledging Option E as a legitimate prototype or incremental deployment path.

**Correction required:** Define the explicit conditions under which E becomes inadequate (e.g., no crash recovery between deployments, manual retry burden exceeds 30 min/incident, publication volume exceeds threshold). This supports an informed human decision about whether to start with E and migrate to A.

---

### FINDING-009 (MINOR) — Temporal Dual-Authority Analysis Is Both Penalized in Matrix and Acknowledged as Solvable in Red Team

**Location:** §5 Option D; §20 Red Team Attack Surface

**Finding:** The analysis penalizes Temporal on Driver 3 (PG Transaction Integration) with a score of 2, citing the dual-authority concern. It then acknowledges in §20 that this concern may be solvable by designing Temporal as an orchestrator that delegates state writes to application use cases.

This is internally inconsistent. If the concern is solvable by design, the penalty on Driver 3 should reflect "solvable with design discipline" (score 3) rather than "structurally difficult" (score 2). The current treatment both overstates and then softens the concern in different sections.

**Correction required:** Either commit to the dual-authority concern as a structural problem (keep score 2, remove the acknowledgment that it's solvable) or revise it as a design discipline concern (update score to 3 and document the correct Temporal integration pattern). The analysis must be internally consistent.

---

### FINDING-010 (MINOR) — Scenario S2 (Duplicate Execution) Is Underdeveloped

**Location:** §7 Failure-Mode Analysis, Scenario S2

**Claim reviewed:**
> "CAS returns 0 rows → exit gracefully. No damage."

**Finding:** The analysis correctly identifies the CAS guard as the defense. However, it omits two edge cases:

1. **Orphaned duplicate jobs in the queue.** When duplicate delivery occurs and one job succeeds (CAS = 1 row), the other job fails the CAS (0 rows) and exits. However, the failed job's Procrastinate record enters a `failed` state. Over time, failed-CAS job records accumulate in the `procrastinate_jobs` table and `procrastinate_events` table. These are not semantically failed jobs — they are idempotent exits — but they will appear as failures in any operational monitoring. The team must distinguish "failed job" from "idempotent exit" in observability tooling.

2. **The CAS correctness requirement.** The claim "CAS returns 0 rows → exit gracefully" assumes that every use case is correctly implemented with CAS. This is an application discipline requirement. The analysis should call this out as a mandatory implementation pattern, not assume it.

---

### FINDING-011 (MINOR) — Driver 9 (Domain Independence) Gives Equal Scores to All Options

**Location:** §14 Decision Matrix

**Observation:** All options receive a score of 5 on Driver 9 (Domain Independence). This is correct in principle — domain independence is achievable by any option if the hexagonal architecture is respected. However, it means Driver 9 contributes identical weight to all options' totals and has no discriminating power in the matrix.

**This is not wrong, but it should be acknowledged:** Driver 9 is a quality floor requirement, not a differentiator. Including it in the weighted matrix inflates all scores equally without affecting relative ranking. The analysis should note this explicitly to avoid the appearance that all options are equally strong on an important dimension.

---

### FINDING-012 (MINOR) — Scheduling Analysis Does Not Address Concurrent Periodic Task Workers

**Location:** §10 Scheduling Analysis; §7 Scenario S7

**Finding:** Procrastinate supports periodic tasks (cron-style). The analysis does not address what happens when multiple Procrastinate worker instances are running concurrently and all have the same periodic task registered. Will multiple workers each trigger the same periodic job at the same scheduled time, creating duplicate executions?

**For Procrastinate specifically:** Procrastinate prevents duplicate periodic task executions through a lock mechanism in the `procrastinate_periodic_defers` table. (FACT — Procrastinate documentation) However, the analysis does not document this, leaving the reader uncertain about multi-worker periodic task safety.

**Correction required:** Add a note confirming Procrastinate's duplicate-safe periodic task mechanism. This is a verification requirement before acceptance.

---

## 4. Observations

### OBSERVATION-001 — Retry Taxonomy Is a Genuine Analytical Contribution

**Location:** §9 Retry / Recovery Analysis

**Claim:** The analysis correctly distinguishes four retry types and maps them to the SDD and ADR-002 framework. The distinction between "technical retry" (same call, same ContentVersion), "publication recovery" (new PublicationAttempt), and "editorial regeneration" (new ContentVersion) is architecturally sound and adds analytical value. (FACT — consistent with SDD §15 and ADR-002 §Publication Recovery Protocol)

**Status:** Survives review. No correction required.

---

### OBSERVATION-002 — Decision Matrix Weighting Is Correctly Structured

**Location:** §14 Decision Matrix

**Observation:** The 3×/2×/1× weighting by driver criticality is consistent with the methodology established in ADR-002's analysis process. The Critical drivers (1, 2, 3) correctly capture the three most architecturally significant dimensions for this ADR. No double-counting is detected across the 13 drivers.

**Status:** Survives review. The non-duplication requirement is satisfied.

---

### OBSERVATION-003 — Option B-RQ Elimination Is Correct

**Location:** §5 Option B, B3 (RQ)

**Claim:** RQ is eliminated because workers are synchronous and incompatible with the asyncio architecture.

**Status:** Survives review. This is a FACT: RQ workers do not support `async def` functions natively. Eliminating RQ is architecturally correct given ADR-001's Python asyncio context. No correction required.

---

### OBSERVATION-004 — The Analysis Correctly Defers Specific Configuration Parameters

**Location:** §17 Unknowns; §16 Risks

**Observation:** The analysis correctly identifies article volume, Redis deployment environment, and platform idempotency keys as unknowns that do not block the analysis. It does not attempt to decide these. This is consistent with the methodology established in ADR-002.

**Status:** Survives review.

---

## 5. Claimed Decisions That Are Actually Architectural Consequences

The following items are presented as if the human decision-maker must evaluate them independently. They are actually automatic consequences of the primary technology choice:

| Item | Status | Reason |
| :--- | :--- | :--- |
| "Procrastinate periodic tasks for recovery scans" | Architectural consequence of choosing A | Not a separate decision |
| "Workers must not hard-delete audited entities" | Already locked by ADR-002 Invariant 3 | Not a queue-layer decision |
| "Job payload serialization (Pydantic)" | Implementation detail | Not an ADR-003 architectural decision |
| "asyncio.gather() for parallel platform generation" | Application design pattern | Not queue-technology-dependent |
| "Dead-letter jobs stored in PG table (Option A)" | Automatic consequence of PG-native queue | Not a separate human choice |

---

## 6. Genuine Human Decision Points

After removing architectural consequences and implementation details, the genuine decisions requiring human input are:

| # | Decision | Why Human Input Is Required |
| :--- | :--- | :--- |
| 1 | **Primary queue technology** (A vs. B-TaskIQ vs. others) | Strategic infrastructure choice; non-trivial reversal cost |
| 2 | **Accept Procrastinate's community/maturity risk** | Smaller ecosystem than Celery; if maintenance is abandoned, migration is a medium-effort operation |
| 3 | **Acceptable stall window for S3 recovery** (if Options B/C/D chosen) | Business risk tolerance; depends on publication SLA not defined in PRD |
| 4 | **Start with E and migrate, or start with A** | Phased approach question; tradeoff between prototype speed and architectural correctness |

---

## 7. Summary of Findings

| ID | Severity | Title | Resolution Required? |
| :--- | :---: | :--- | :---: |
| F-001 | 🔴 CRITICAL | "Structurally impossible" S3 claim is overstated | Yes — revise to "achievable with correct integration" |
| F-002 | 🔴 CRITICAL | Dual recovery path divergence not modeled | Yes — define TTL ordering invariant |
| F-003 | 🟠 MAJOR | Schema migration coupling not addressed | Yes — document Alembic exclusion requirement |
| F-004 | 🟠 MAJOR | PostgreSQL unavailability → full system halt not acknowledged | Yes — document availability trade-off |
| F-005 | 🟠 MAJOR | Job table maintenance not addressed | Yes — document pruning requirement |
| F-006 | 🟠 MAJOR | S3 recovery scan complexity understated for B/C/D | Yes — qualify as non-trivial implementation |
| F-007 | 🟠 MAJOR | Celery rejection evidence partially stale/imprecise | Yes — clarify primary rejection reason |
| F-008 | 🟡 MINOR | Option E inadequacy lacks threshold definition | Yes — define failure threshold |
| F-009 | 🟡 MINOR | Temporal dual-authority: penalized in matrix, softened in Red Team | Yes — make internally consistent |
| F-010 | 🟡 MINOR | S2 duplicate job observability gap | Recommended — add monitoring note |
| F-011 | 🟡 MINOR | Driver 9 scores equally for all options (no discriminating power) | Recommended — acknowledge explicitly |
| F-012 | 🟡 MINOR | Concurrent periodic task worker safety not verified | Yes — verify Procrastinate lock mechanism |

**Claims that survive review (no correction required):** OBSERVATION-001 through OBSERVATION-004.

---

## 8. Acceptance Recommendation

### Verdict: CONDITIONAL

The ADR-003 Analysis may proceed to the Red Team phase under the following conditions:

**Mandatory corrections before Red Team:**

1. **F-001:** Revise "structurally impossible" to "achievable through correct transactional integration, requiring explicit application-layer discipline." Document the invariant: *defer call must be inside the same `session.begin()` context as the CAS + audit INSERT.*

2. **F-002:** Add a new failure scenario: "Dual Recovery Path Divergence — Procrastinate heartbeat TTL vs. ADR-002 PUBLISHING TTL." Specify that PUBLISHING TTL must be longer than Procrastinate heartbeat timeout + one recovery scan interval to prevent competing recovery mechanisms.

3. **F-004:** Add an explicit availability trade-off statement: "Option A couples queue availability to database availability. This is acceptable for the JincSAE MVP because PostgreSQL downtime also halts all domain operations, but must be stated for the human decision record."

**Recommended corrections (may be addressed in Reconciliation if Red Team proceeds):**

1. **F-003:** Document Alembic autogenerate exclusion requirement for Procrastinate tables.
2. **F-005:** Add a Procrastinate job table maintenance policy requirement.
3. **F-006:** Qualify S3 recovery scan as non-trivial for Options B/C/D.
4. **F-007:** Restate Celery's primary rejection reason as Driver 3, not asyncio.
5. **F-008:** Define an explicit Option E failure threshold.
6. **F-009:** Resolve the Temporal dual-authority inconsistency in the matrix.
7. **F-012:** Verify and document Procrastinate's concurrent periodic task deduplication mechanism.

**The preliminary recommendation of Option A (Procrastinate) survives review**, but its primary justification must be reformulated. The recommendation is technically sound; the language used to express it is not.
