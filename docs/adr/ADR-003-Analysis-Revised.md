---
adr-id: ADR-003
title: "Async Processing, Background Jobs & Workflow Execution — Analysis (Revised)"
status: PROPOSED — UNDER ARCHITECTURAL REVIEW
phase: Analysis (Post Architecture Review Remediation)
supersedes: docs/adr/ADR-003-Analysis.md
remediation-of: docs/adr/ADR-003-ArchReview.md
authority-chain:
  - docs/ENGINEERING_CONSTITUTION.md
  - docs/PRD.md
  - docs/SDD.md
  - docs/adr/ADR-001-Runtime-Language.md
  - docs/adr/ADR-002-Persistence-Strategy.md
  - docs/adr/MASTER_BRIEFING_ADR-003_ASYNC_PROCESSING.md
original-analysis: docs/adr/ADR-003-Analysis.md
arch-review: docs/adr/ADR-003-ArchReview.md
created-at: 2026-09-01
---

# ADR-003 Analysis — Revised

# Async Processing, Background Jobs & Workflow Execution

---

## Architecture Review Remediation Index

This section is the formal remediation record. It precedes the analysis body
so reviewers can verify finding disposition before reading the full document.

| Finding | Severity | Title | Disposition |
| :--- | :---: | :--- | :--- |
| F-001 | 🔴 CRITICAL | "Structurally impossible" S3 claim overstated | **RESOLVED** — §8 rewritten; new invariant defined |
| F-002 | 🔴 CRITICAL | Dual recovery path divergence not modeled | **RESOLVED** — §8.2 defines Single Recovery Authority Protocol |
| F-003 | 🟠 MAJOR | Schema migration coupling | **RESOLVED** — §12.3 addresses Alembic isolation requirement |
| F-004 | 🟠 MAJOR | PostgreSQL unavailability trade-off undeclared | **RESOLVED** — §12.4 declares the coupled-availability property |
| F-005 | 🟠 MAJOR | Job table maintenance unaddressed | **RESOLVED** — §12.5 defines retention/pruning ownership |
| F-006 | 🟠 MAJOR | Recovery complexity understated | **RESOLVED** — §9 recovery taxonomy fully expanded |
| F-007 | 🟠 MAJOR | Celery rejected for wrong reason | **RESOLVED** — §5.3 restates Celery evaluation on correct drivers |
| F-008 | 🟡 MINOR | Option E inadequacy lacks threshold | **PARTIALLY RESOLVED** — threshold defined; exact volume deferred |
| F-009 | 🟡 MINOR | Temporal dual-authority inconsistency | **RESOLVED** — scoring and rationale aligned |
| F-010 | 🟡 MINOR | S2 duplicate job observability gap | **RESOLVED** — §7.2 adds monitoring note |
| F-011 | 🟡 MINOR | Driver 9 no discriminating power | **RESOLVED** — acknowledged in matrix notes |
| F-012 | 🟡 MINOR | Concurrent periodic task safety unverified | **RESOLVED** — §10 documents Procrastinate deduplication mechanism |

**Claims from original analysis that survive review without correction:**

- Retry taxonomy (4 types: technical / worker recovery / domain recovery / editorial regeneration)
- Decision matrix non-duplication across 13 drivers
- RQ elimination (synchronous workers, asyncio-incompatible)
- Unknown/deferred decision boundaries

---

## 1. Executive Summary

The JincSAE requires an asynchronous execution layer for a multi-stage, LLM-assisted editorial pipeline from article ingestion through publication to external social media platforms. This revised analysis addresses all findings raised by the independent Architecture Review (`ADR-003-ArchReview.md`) and restates the preliminary recommendation with corrected evidence language.

**The central architectural question remains:**

> How can a committed domain state transition reliably cause asynchronous downstream work without creating a dual-write inconsistency between PostgreSQL state and the job queue?

This question — the Lost Dispatch Problem (Scenario S3) — is the primary differentiator between the five candidates. Its resolution depends directly on ADR-002's invariants, particularly Invariant 1 (atomic transaction boundary) and the principle that PostgreSQL is the authoritative source of domain state.

**Revised Preliminary Recommendation:** Option A (Procrastinate) remains the strongest technical candidate. However, its primary advantage — transactional enqueue — is **not an automatic guarantee of selecting Procrastinate**. It is achievable only when the Transactional Dispatch Invariant (defined in §8.1) is correctly implemented. The recommendation is conditional on that invariant being enforced at the application layer.

Additionally, two recovery mechanisms (Procrastinate worker heartbeat and ADR-002 PUBLISHING domain recovery) must operate under a Single Recovery Authority Protocol (§8.2) to prevent race conditions. This protocol is now formally defined.

**Status:** `PROPOSED — UNDER ARCHITECTURAL REVIEW`

---

## 2. Decision Context

### 2.1 System Nature

The JincSAE is a Python-based (ADR-001: Accepted) editorial automation engine. Its pipeline is inherently asynchronous: article analysis, LLM generation calls, content validation, and social platform publication all involve I/O operations with unpredictable latency.

The pipeline has two distinct operational profiles:

**High-latency, sequential, LLM-dependent pipeline:**

```
Article Ingestion (webhook)
    → AnalyzeArticle (LLM: ~5–60s)
    → GenerateEditorialBrief (LLM: ~5–30s)
    → GeneratePlatformContent × N platforms (LLM: ~5–30s each)
    → RunContentValidation (~1–5s)
    → Await Human Approval (unbounded)
```

**Reliability-critical publication pipeline:**

```
ContentVersion approved
    → SCHEDULED state [CAS + audit — 1 DB tx]
    → PUBLISHING state [CAS + audit + PublicationAttempt INSERT — 1 DB tx]
    → External platform API call [outside DB transaction — residual risk per ADR-002]
    → PUBLISHED or PUBLISH_FAILED [CAS + audit + PublicationAttempt UPDATE — 1 DB tx]
    → Recovery scan [periodic, PUBLISHING TTL-based]
```

### 2.2 Workload Characterization

The PRD does not specify a target article volume, concurrent user count, or jobs-per-second requirement. (FACT: PRD examined; no volume SLA defined.)

**Conservative MVP estimate:** A single journalistic newsroom, small editorial team. (INFERENCE: from PRD product vision — single publication, not multi-tenant SaaS at launch.)

Assumed workload profile:

- Articles per day: low double digits (ASSUMPTION)
- Platforms per article: 4 → 4 generation jobs per article
- Concurrent LLM calls: low single digits
- Peak publication jobs: low tens per day
- Recovery scans: periodic, minutes interval

**The JincSAE MVP does not require high-throughput queue infrastructure.** Throughput is not a primary decision driver. (INFERENCE from PRD workload estimate.)

### 2.3 Accepted Constraints

From ADR-001: Python + asyncio. All options must be Python-native.
From ADR-002: 7 locked invariants, detailed in §3.

---

## 3. Locked Constraints (Non-Negotiable)

### 3.1 From ADR-001 — Python Runtime

All async options must be Python-compatible. asyncio is the preferred I/O model. Node.js-native solutions are excluded. (FACT)

### 3.2 From ADR-002 — PostgreSQL + Hybrid Audit (7 Invariants)

| # | Invariant | Impact on ADR-003 |
| :--- | :--- | :--- |
| 1 | CAS UPDATE + audit INSERT in one explicit DB transaction | Workers executing state transitions must do so atomically within a single `session.begin()` block |
| 2 | Audit history is append-only | Workers INSERT new rows; never UPDATE existing audit records |
| 3 | Audited entities use soft-delete | Workers must not hard-delete entities with audit chains |
| 4 | Regeneration creates a new ContentVersion | A "retry generation" job must create a new entity, not overwrite |
| 5 | PublicationAttempt is immutable | Workers do not modify status of existing PublicationAttempt rows once created |
| 6 | Retry = new PublicationAttempt record | Each retry creates a new INSERT; workers do not UPDATE to retry |
| 7 | Domain layer must not import queue infrastructure | Queue libraries are confined to the infrastructure layer |

### 3.3 Core Principle

> **The async/job system executes work. PostgreSQL remains the authoritative source of domain state.**

Workers may fail, restart, or be duplicated. Correctness depends on: persisted state, transaction boundaries, CAS concurrency guards, idempotent use cases, and explicit retry policies. The queue must never become the source of truth.

---

## 4. Decision Drivers

The following 13 drivers are non-overlapping. Each covers a distinct concern. No driver appears twice.

| # | Driver | Weight | Definition |
| :--- | :--- | :---: | :--- |
| 1 | Operational Simplicity | Critical (3×) | Count of infrastructure services required beyond PostgreSQL |
| 2 | Python & asyncio Compatibility | Critical (3×) | Native asyncio support; `async def` jobs without thread-pool workaround |
| 3 | PostgreSQL Transaction Integration | Critical (3×) | Ability to enqueue jobs within a PostgreSQL transaction; achievability of the Transactional Dispatch Invariant |
| 4 | Crash Recovery | High (2×) | Job recoverability when worker crashes mid-execution |
| 5 | Retry Semantics | High (2×) | At-least-once delivery; exponential backoff with jitter; max retry; dead-letter |
| 6 | Delayed & Scheduled Execution | High (2×) | Native enqueue with future datetime |
| 7 | Idempotent Execution Support | High (2×) | Duplicate delivery safety; CAS compatibility |
| 8 | Observability | High (2×) | Job status; failure logs; queue depth; worker health |
| 9 | Domain Independence | High (2×) | Queue library confined to infrastructure layer |
| 10 | Development & Testing Complexity | Medium (1×) | Local setup; unit testability without broker |
| 11 | Scalability | Medium (1×) | MVP to small newsroom scale without architectural change |
| 12 | Reversibility | Medium (1×) | Migration cost if option needs replacement |
| 13 | Vendor/Infrastructure Lock-in | Medium (1×) | Proprietary service dependency |

**Note on Driver 9:** Domain independence is achievable by any option if hexagonal architecture is respected. It functions as a quality floor requirement (score 5 for all options), not a differentiator. This is acknowledged explicitly. Its inclusion in the matrix ensures it is formally verified, not assumed. (OBSERVATION-001 from Architecture Review, retained)

**Prohibited drivers:** popularity, team familiarity, industry standard status.

---

## 5. Candidate Strategies

### 5.1 Option A — Procrastinate (PostgreSQL-Native Queue)

**Description:** Procrastinate is a Python asyncio-native task queue that uses PostgreSQL as the job broker. Jobs are rows in PostgreSQL tables. Workers use PostgreSQL `LISTEN/NOTIFY` for efficient push-based wake-up, with periodic polling fallback.

**Key architectural property:** Jobs can be enqueued by INSERT into the Procrastinate job table within the same SQLAlchemy database session (and therefore the same transaction) as the domain state change. This property is the basis for the Transactional Dispatch Invariant defined in §8.1.

**Critical caveat (F-001 remediation):** This property is NOT automatic merely by selecting Procrastinate. It requires correct implementation of the transactional integration pattern. See §8.1 for the full invariant specification and the conditions under which it can be violated.

**Infrastructure dependencies:** PostgreSQL (already required by ADR-002). No additional service required. (FACT)

**asyncio support:** Native; `async def` task functions. (FACT)

**Delayed/scheduled execution:** `schedule_in` and `schedule_at` parameters on task dispatch. (FACT — Procrastinate documentation)

**Retry semantics:** Configurable per-task `RetryStrategy` with max retries, delays, and exponential backoff with jitter. (FACT — Procrastinate documentation)

**Scheduled periodic tasks:** Procrastinate supports cron-style periodic tasks. Multiple concurrent worker instances use the `procrastinate_periodic_defers` table to prevent duplicate periodic task execution. (FACT — Procrastinate documentation; remediates F-012)

**Schema impact:** Adds 4 tables to PostgreSQL: `procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`, `procrastinate_versions`. Schema migration coupling concern addressed in §12.3 (F-003 remediation).

**Maturity:** Actively maintained; v2.x production-ready; documented production usage. (FACT)

**Worker crash recovery:** The `procrastinate_jobs` table records job status as `doing` during execution. Workers send heartbeats. If a worker crashes and the heartbeat lapses beyond the configured timeout, the job is automatically re-queued. The exact interaction with ADR-002's PUBLISHING state recovery is formally defined in the Single Recovery Authority Protocol (§8.2), remediating F-002.

**Job table maintenance:** Completed and failed jobs accumulate in `procrastinate_jobs` and `procrastinate_events` unless pruned. Retention policy and operational ownership defined in §12.5 (F-005 remediation).

**Availability coupling:** PostgreSQL unavailability halts both persistence and the queue. This trade-off is explicitly declared in §12.4 (F-004 remediation).

**FastAPI integration:** Lifecycle managed via FastAPI lifespan events. (FACT — Procrastinate documentation)

---

### 5.2 Option B — Redis-Backed Async Python Queue

**Sub-candidates evaluated (RQ eliminated at entry — see §5.2.3):**

#### 5.2.1 ARQ (asyncio Redis Queue)

ARQ is an asyncio-native, Redis-backed task queue.

**asyncio support:** Native. `async def` job functions. (FACT)
**Redis requirement:** Redis 5.0+. Adds one infrastructure service. (FACT)
**Delayed execution:** `defer_by` / `defer_until`. (FACT)
**Retry semantics:** `max_tries` supported. Built-in exponential backoff with jitter is NOT included — must be implemented in the task function manually. (FACT — ARQ documentation; this is a material gap relative to Procrastinate)
**Dead-letter:** No native DLQ. Failed jobs tracked via `max_tries` exhaustion but require custom tracking. (FACT — Engineering Constitution §15 "No Silent Failure" creates tension with this gap)
**Crash recovery:** ARQ uses a health-check mechanism; jobs in-flight re-queued after configurable timeout. Recovery depends on Redis durability configuration. (FACT)
**Redis durability:** With `appendfsync everysec` (default), up to 1 second of enqueued jobs can be lost on crash. `appendfsync always` eliminates this but reduces throughput. (FACT — Redis persistence documentation)
**Scheduler crash:** Scheduled jobs (sorted sets in Redis) are subject to the same Redis durability constraint. With default configuration, scheduled future publications can be lost on Redis crash. (FACT — material gap for publication scheduling reliability)

#### 5.2.2 TaskIQ

TaskIQ is a modern asyncio-native task queue with pluggable brokers.

**asyncio support:** Native. (FACT)
**Broker flexibility:** Redis, NATS, RabbitMQ, in-memory, and others. (FACT)
**Retry semantics:** Built-in retry with configurable backoff. (FACT)
**Dead-letter:** Configurable per broker. (FACT)
**Maturity:** Newer library; smaller community than ARQ or Celery. (FACT)

#### 5.2.3 RQ (Redis Queue) — Eliminated

RQ workers are synchronous Python processes. Running `async def` functions requires `asyncio.run()` inside the sync worker, creating a new event loop per job. This is incompatible with a shared async SQLAlchemy connection pool and the asyncio architecture established by ADR-001. (FACT — RQ documentation; architectural incompatibility) **RQ is eliminated. No further analysis.**

**Option B summary:** ARQ and TaskIQ are the viable sub-candidates. Both require Redis as an additional infrastructure service. Both create the Lost Dispatch risk (Scenario S3) because job enqueue is a Redis write that cannot participate in a PostgreSQL transaction. Both require a compensating recovery scan — whose complexity is quantified in §9.3 (F-006 remediation).

---

### 5.3 Option C — Celery (Revised Evaluation — Remediates F-007)

**F-007 Remediation:** The original analysis cited incomplete asyncio support as the primary rejection reason. The Architecture Review correctly identified this as imprecise. The primary architectural reason to reject Celery for the JincSAE MVP is Driver 3 (PostgreSQL Transaction Integration), not asyncio compatibility. Celery's asyncio evaluation is secondary.

**Primary rejection reason — Driver 3 (PostgreSQL Transaction Integration):**

Celery does not participate in PostgreSQL transactions. There is no mechanism in Celery to enqueue a task atomically within a `session.begin()` block. The standard Celery pattern is `task.apply_async()` after `db.commit()`. This is a non-atomic dual-write. For Options B and C, this creates the Lost Dispatch Problem (Scenario S3), requiring a compensating recovery scan. (FACT — Celery architecture; there is no transactional broker integration mechanism in Celery)

This is the same S3 exposure as Redis-backed options. However, Celery additionally requires 2–4 infrastructure services for the MVP:

| Celery Component | Service | Required? |
| :--- | :--- | :--- |
| Message broker | RabbitMQ or Redis | Mandatory |
| Result backend | Redis or PostgreSQL | Mandatory for task status |
| Celery Beat | Separate process | Required for periodic/scheduled tasks |
| Flower | Separate service | Required for observability |

**Secondary evaluation — asyncio compatibility:**

Celery 5.x has introduced asyncio worker support (`--pool=asyncio`), but this is not functionally equivalent to ARQ or Procrastinate's native asyncio model. Celery's asyncio pool requires explicit integration patterns and has known limitations in sharing resources (e.g., SQLAlchemy async sessions) across task boundaries. (INFERENCE — from Celery 5.x documentation and known integration patterns; marked INFERENCE because Celery's asyncio support may improve across versions)

**Verdict:** Celery is rejected for the JincSAE MVP on Driver 3 (inability to participate in PostgreSQL transactions) and Driver 1 (2–4 required infrastructure services disproportionate to MVP workload). The asyncio concern is a secondary supporting factor, not the primary reason.

---

### 5.4 Option D — Temporal (Revised Evaluation — Remediates F-009)

**F-009 Remediation:** The original analysis penalized Temporal on Driver 3 (score: 2, citing dual-authority concern) but acknowledged in §20 that the concern could be resolved by careful design. This was internally inconsistent. The revised evaluation resolves this.

**Temporal integration model — two viable patterns:**

**Pattern D1 (Rejected):** Temporal owns workflow state, domain state is derived from Temporal. This creates a dual-authority conflict with ADR-002's principle that PostgreSQL is the authoritative state store. Not a viable pattern for JincSAE.

**Pattern D2 (Viable but complex):** Temporal acts as a pure orchestrator. All domain state transitions are performed by Temporal Activities that call JincSAE application use cases. PostgreSQL remains authoritative. Temporal holds only orchestration state (which activity to call next, retry counts, timers).

Under Pattern D2, Temporal does not own domain state. The dual-authority concern is resolved by design. However, this requires:

1. Every domain transition to be implemented as a Temporal Activity.
2. Careful separation of Temporal's orchestration state from JincSAE's domain state.
3. Temporal Activities must implement the CAS guard correctly.
4. The development team must learn Temporal's programming model (deterministic workflow code, signal handling, etc.).

**Revised Driver 3 score for Temporal (Pattern D2):** 3 (achievable by design, but not structural; requires significant discipline and Temporal-specific patterns). This resolves the F-009 inconsistency.

**Infrastructure:** Temporal Server + Temporal's own persistence store + Temporal Web UI. Minimum 2–3 additional services. (FACT)

**MVP proportionality assessment:** Temporal's primary value is in long-running sagas with complex branching, external wait states, and multi-system coordination. The JincSAE pipeline has human-in-the-loop wait states (human approval), but these are modeled trivially via PostgreSQL state without requiring Temporal's durable workflow machinery. Temporal's additional complexity is not justified by the current PRD scope. (INFERENCE — consistent with Master Briefing §5.4 burden of proof requirement)

---

### 5.5 Option E — Application-Native Scheduling (Revised Evaluation — Remediates F-008)

**F-008 Remediation:** The original analysis stated "unsuitable for production" without defining the failure threshold. This is corrected.

**Operational model:** FastAPI `BackgroundTasks` or an asyncio polling loop within the API process. No separate worker process. No external broker.

**Explicit failure threshold — Option E becomes inadequate when any of the following is true:**

| Condition | Why It Forces Migration |
| :--- | :--- |
| Article processing volume causes background tasks to starve the API event loop | In-process execution competes with request handling for the asyncio thread |
| A publication failure requires detection within < N minutes (N to be defined operationally) | No background worker = detection only at API startup or explicit scan trigger |
| A process crash between DB commit and in-process dispatch creates a stall that is undetectable for > 1 deployment cycle | No persistent job record; stall is invisible until next startup scan |
| The team needs distinct retry policies per job type | No framework; each policy requires bespoke implementation |
| Dead-letter tracking is required (Constitution §15 — No Silent Failure) | No framework-provided dead-letter mechanism |

**Assessment:** Option E is a viable starting point for a prototype phase or pre-MVP, not a production queue strategy. It is explicitly not recommended as the primary option. The threshold for mandatory migration is when any condition in the table above is reached.

---

## 6. Comparative Analysis

### 6.1 PostgreSQL Transaction Integration (Critical Driver)

| Option | Transactional Enqueue Possible? | S3 Risk | Mechanism |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ YES — **when Transactional Dispatch Invariant is implemented** | Eliminated by implementation (not by mere library selection) | Job = PG INSERT in same session.begin() |
| B — ARQ / TaskIQ | ❌ NO | Exists; requires recovery scan | Redis write is external to PG transaction |
| C — Celery | ❌ NO | Exists; requires recovery scan | Broker write is external to PG transaction |
| D — Temporal (P2) | ❌ NO | Exists; requires recovery scan | Temporal SDK call is external to PG transaction |
| E — App-native | ⚠️ PARTIAL | Reduced if in-process, but process crash creates stall | No persistent job record |

(FACT for A conditional; FACT for B/C/D external broker; INFERENCE for E)

### 6.2 Infrastructure Services Required

| Option | Additional Services Beyond PG | Local Dev Overhead |
| :--- | :--- | :--- |
| A — Procrastinate | 0 | 0 |
| B — ARQ | 1 (Redis) | 1 container |
| B — TaskIQ | 1 (Redis, default) | 1 container |
| C — Celery | 2–4 (broker + result backend + Beat + Flower) | 2–4 containers |
| D — Temporal | 2–3 (Temporal server + its DB + Web UI) | 2–3 containers |
| E — App-native | 0 | 0 |

(FACT — based on documented deployment requirements)

### 6.3 asyncio Compatibility

| Option | Native asyncio | async def jobs | Assessment |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ Full | ✅ Yes | Excellent |
| B — ARQ | ✅ Full | ✅ Yes | Excellent |
| B — TaskIQ | ✅ Full | ✅ Yes | Excellent |
| B — RQ | ❌ No | ❌ No | Eliminated |
| C — Celery | ⚠️ Partial/Evolving | ⚠️ Via asyncio pool | Secondary concern — primary rejection is Driver 3 |
| D — Temporal | ✅ Full | ✅ Yes | Good |
| E — App-native | ✅ Full | ✅ Yes | Excellent |

(FACT for Procrastinate, ARQ, TaskIQ; INFERENCE for Celery asyncio pool status — version-dependent)

---

## 7. Failure-Mode Analysis

### 7.1 Scenario S1 — Worker Crash After Job Claim

| Option | Recovery Mechanism | Automatic? | Notes |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | Heartbeat TTL on `doing` job; automatic re-queue on timeout | ✅ Yes | Recovery ordering relative to PUBLISHING domain scan defined in §8.2 |
| B — ARQ | Redis visibility timeout; re-queue after timeout | ✅ Yes | Depends on Redis durability config for schedule integrity |
| B — TaskIQ | Broker visibility timeout; varies by broker | ✅ Yes | |
| C — Celery | `acks_late=True` + visibility timeout | ✅ Yes | Requires broker configuration |
| D — Temporal | Temporal server detects worker disconnect; activity retried | ✅ Yes | Temporal is responsible for activity retry |
| E — App-native | None during run; startup scan re-discovers stuck entities | ⚠️ On restart only | Window = downtime duration |

---

### 7.2 Scenario S2 — Duplicate Execution (Remediates F-010)

All options deliver at-least-once semantics. Duplicate execution is possible in all cases. The JincSAE defense is application-level:

**CAS guard:** `UPDATE ... WHERE status = 'X'` ensures only one actor completes a given transition. A duplicate job execution that arrives after the first has already transitioned state will find `rows_affected = 0` and exit without effect. (FACT — ADR-002 §Concurrency Model)

**Observability note (F-010 remediation):** When a duplicate job exits via CAS returning 0 rows, the Procrastinate job record enters `failed` state if no special handling is implemented. Over time, CAS-rejected jobs will appear as failures in monitoring dashboards. The application must either:

1. Catch the "0 rows affected" condition and mark the job as `succeeded` explicitly (via Procrastinate's job completion API), or
2. Document and configure monitoring to distinguish "CAS-rejected idempotent exit" from "genuine failure."

This is a monitoring discipline requirement that must be addressed in the observability specification.

---

### 7.3 Scenario S3 — DB Commits, Job Dispatch Fails (Revised — Remediates F-001 and F-006)

**This scenario is the primary differentiator. Its analysis is expanded in §8 (Transaction/Queue Consistency Analysis).**

Summary:

| Option | S3 Eliminated? | Cost |
| :--- | :--- | :--- |
| A — Procrastinate | ✅ Eliminated — **when Transactional Dispatch Invariant correctly implemented** | Application-layer discipline; see §8.1 |
| B — ARQ / TaskIQ | ❌ No | Recovery scan required; non-trivial to implement correctly; see §9.3 |
| C — Celery | ❌ No | Same as B |
| D — Temporal | ❌ No | Same pattern; Temporal SDK call is post-commit |
| E — App-native | ⚠️ Reduced | In-process dispatch is within same asyncio task; crash still creates stall |

---

### 7.4 Scenario S4 — Job Dispatched, DB Transaction Rolls Back

A worker receives a job referencing state that never committed.

**Defense (all options):** The use case executes a CAS update: `UPDATE ... WHERE id = $1 AND status = 'EXPECTED'`. If the DB transaction rolled back, the entity is either in a prior state or does not exist. The CAS returns `0 rows`. The worker must treat 0 rows as a graceful exit, not an error requiring retry. This is a mandatory implementation pattern, not an automatic framework behavior. (SUPPORTED INFERENCE — consequence of ADR-002 CAS design)

**Note for Option A:** Under correct transactional integration, S4 cannot occur because the job INSERT rolls back with the transaction. S4 is only possible if a job is enqueued before its transaction commits — which the Transactional Dispatch Invariant explicitly prohibits.

---

### 7.5 Scenario S5 — LLM Provider Timeout

**Retry taxonomy (remediates F-006):**

Two distinct behaviors apply, based on what state was persisted before the timeout:

| Situation | Classification | Action |
| :--- | :--- | :--- |
| LLM call in progress, no content committed yet | Technical retry (infra) | Retry the HTTP call; same ContentVersion; no new entity |
| LLM response received, content committed as ContentVersion | Editorial regeneration (domain event) | New ContentVersion via `RegenerateContentUseCase`; human-initiated |
| LLM call timed out after response was sent by provider (unknown) | Technical retry first | Retry the call; if idempotency key supported by provider, use it; else accept potential duplicate generation as a ContentVersion conflict to be resolved via CAS |

The framework must support per-task configurable retry policies to allow different behavior for LLM jobs vs. publication jobs. (FACT for Procrastinate, TaskIQ, Celery, Temporal; manual for ARQ)

---

### 7.6 Scenario S6 — Publication Timeout

Fully specified in ADR-002 §Publication Recovery Protocol. The async framework must support the TTL-based PUBLISHING recovery scan. This is a periodic job, not a framework-level concern. Integration of this scan with Procrastinate's worker recovery is specified in §8.2 (Single Recovery Authority Protocol).

---

### 7.7 Scenario S7 — Scheduler Crash with Pending Publications

| Option | Schedule Storage | Durability |
| :--- | :--- | :--- |
| A — Procrastinate | `scheduled_at` in `procrastinate_jobs` (PostgreSQL) | Full PostgreSQL ACID durability; no separate configuration required |
| B — ARQ | Redis sorted set | Requires `appendfsync always` for full durability; default config risks 1-second loss |
| B — TaskIQ | Broker-dependent | Varies |
| C — Celery | Celery Beat file/DB | Separate process restart; Beat configuration |
| D — Temporal | Temporal server state | Temporal server restart; Temporal durability guarantees |
| E — App-native | PostgreSQL (`scheduled_at` column on ContentVersion) | Durable; requires startup scan to rediscover |

**Assessment:** Option A provides the strongest scheduler crash story: scheduled jobs are PostgreSQL rows with `scheduled_at`. Worker restart automatically reclaims them. No additional configuration required beyond what ADR-002 already mandates. (FACT for A; FACT for ARQ Redis durability risk; remediates original analysis's understated risk)

---

### 7.8 Scenario S8 — Retry Storm

| Option | Rate Limiting | Exponential Backoff | Jitter | Dead Letter |
| :--- | :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ Per-queue concurrency limit | ✅ RetryStrategy | ✅ Yes | ✅ `failed` status in PG table |
| B — ARQ | ⚠️ Worker concurrency only | ❌ Manual | ❌ Manual | ⚠️ Manual tracking |
| B — TaskIQ | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Configurable |
| C — Celery | ✅ Per-queue rate limits | ✅ Yes | ✅ Yes | ✅ Yes |
| D — Temporal | ✅ Activity rate limits | ✅ Yes | ✅ Yes | ✅ Workflow failure state |
| E — App-native | ❌ Custom | ❌ Custom | ❌ Custom | ❌ Custom |

ARQ's retry storm resistance is the weakest among proper queue frameworks. Constitution §15 (No Silent Failure) requires a dead-letter or permanent failure state. ARQ requires custom implementation for this. (FACT for ARQ; FACT for Constitution requirement)

---

## 8. Transaction / Queue Consistency Analysis (Revised — Remediates F-001 and F-002)

### 8.1 Transactional Dispatch Invariant (F-001 Remediation)

**The claim that Scenario S3 is "structurally impossible" under Procrastinate is replaced by the following formal invariant:**

> **Transactional Dispatch Invariant:** A domain state transition that requires asynchronous execution must not commit without its corresponding job being transactionally registered in the same PostgreSQL transaction.

This invariant is achievable under Procrastinate when the following conditions are all met:

**Condition 1 — Shared Connection:** The Procrastinate async connector must use the same PostgreSQL connection as the SQLAlchemy session. In practice, this requires Procrastinate to be initialized with an `AiopgConnector` or `AsyncpgConnector` that is bound to, or adapted from, the same asyncpg connection pool used by SQLAlchemy. If Procrastinate uses a separate connection, the job INSERT executes in a separate transaction and does not roll back with the domain transaction. (FACT — Procrastinate integration documentation requires explicit connection sharing)

**Condition 2 — Correct Call Placement:** `task.defer_async()` must be called inside the `async with session.begin():` block, after the CAS UPDATE and audit INSERT, but before the block exits (commits). Calling `defer_async()` after the `session.begin()` block exits means the job is dispatched after the domain transaction has already committed — recreating the dual-write problem. (SUPPORTED INFERENCE — follows from Python asyncio context manager semantics and Procrastinate defer mechanics)

**Condition 3 — No Intermediate Commits:** The use case must not call `session.commit()` at any point between the CAS UPDATE and the `defer_async()` call. Intermediate commits break the atomic boundary. Use cases must use a single explicit transaction that covers all three operations: CAS + audit INSERT + defer. (SUPPORTED INFERENCE — consequence of ADR-002 Invariant 1 and transaction boundary semantics)

**Condition 4 — Transaction Rollback Propagates Correctly:** If any operation within the `session.begin()` block raises an exception, the entire block rolls back, including the Procrastinate job INSERT. This is the correct behavior — no job exists for work that was never committed. (FACT — SQLAlchemy async `session.begin()` as a context manager rolls back on exception)

**What S3 looks like under Option A if the invariant is violated:**

```python
# INCORRECT — violates Condition 2: defer called outside transaction
async with session.begin():
    await content_version_repo.transition(cv_id, 'GENERATED', 'VALIDATED', actor='SYSTEM')
    # Transaction commits here
await generate_task.defer_async(content_version_id=str(cv_id))
# ↑ This is a separate operation. If it fails → S3 occurs.

# CORRECT — Transactional Dispatch Invariant satisfied
async with session.begin():
    await content_version_repo.transition(cv_id, 'GENERATED', 'VALIDATED', actor='SYSTEM')
    await generate_task.defer_async(content_version_id=str(cv_id))
# ↑ All committed or all rolled back. S3 is prevented — not by Procrastinate, 
#   but by correct implementation of this invariant.
```

**Implication for Application Architecture:** The Transactional Dispatch Invariant must be enforced at the Repository/Use Case boundary through code review and integration tests. It is a **mandatory implementation constraint**, not an automatic architectural guarantee. Any code review gate must verify that all use cases that dispatch jobs follow this pattern.

**Revised S3 analysis for Option A:** S3 is not "structurally impossible" under Procrastinate. It is **preventable through correct implementation of the Transactional Dispatch Invariant**. When implemented correctly, Option A provides structural prevention of S3. If violated, Option A provides no more S3 protection than Options B, C, or D.

---

### 8.2 Single Recovery Authority Protocol (F-002 Remediation)

**The Problem:** When a Procrastinate worker crashes after completing the CAS domain state transition but before completing the external side-effect (or in any intermediate state), two independent recovery mechanisms can fire:

- **Worker-side recovery:** Procrastinate heartbeat TTL expires → job status reset from `doing` to `queued` → job re-dispatched to a new worker.
- **Domain-side recovery:** ADR-002 PUBLISHING TTL scan fires → `ContentVersion.status = PUBLISHING` beyond TTL → recovery protocol resets PUBLISHING to SCHEDULED and creates a new PublicationAttempt.

If these two mechanisms fire concurrently or in the wrong order, the following race condition can occur:

```
T=0   Worker claims job. CAS: SCHEDULED → PUBLISHING. PublicationAttempt created.
T=1   Worker crashes. Procrastinate job status = 'doing'.
T=2   ADR-002 recovery scan fires (PUBLISHING TTL exceeded).
T=3   Scan: CAS PUBLISHING → SCHEDULED. New PublicationAttempt created.
T=4   Procrastinate heartbeat TTL fires. Job re-queued as 'queued'.
T=5   New worker picks up original job. CAS: SCHEDULED → PUBLISHING.
      — Succeeds: entity was reset to SCHEDULED by the scan.
      — Two workers now competing for the same publication dispatch.
      — One will create a new PublicationAttempt (correct).
      — The original job's PublicationAttempt (from T=0) is orphaned.
```

**Single Recovery Authority Protocol:**

The following protocol resolves the race condition by establishing clear ownership and ordering:

**Rule 1 — Worker Recovery Has Priority:**

The Procrastinate heartbeat TTL must expire and trigger job re-queue BEFORE the ADR-002 PUBLISHING recovery scan is eligible to act on a PUBLISHING entity. The PUBLISHING TTL must be strictly greater than the Procrastinate heartbeat TTL plus the scan polling interval:

```
PUBLISHING_TTL > (Procrastinate_Heartbeat_TTL + Recovery_Scan_Interval + Safety_Margin)
```

**Rationale:** If the Procrastinate heartbeat fires first, the job is re-queued. The new worker picks it up and either completes the publication (success) or fails definitively (→ PUBLISH_FAILED). The PUBLISHING recovery scan will then observe a non-stuck entity and take no action. The domain recovery scan never needs to compete with an active Procrastinate recovery.

**Rule 2 — Domain Recovery Scan Uses CAS:**

When the PUBLISHING recovery scan does act (i.e., PUBLISHING TTL has expired AND no active Procrastinate job exists for this entity), it must use CAS to transition the domain state:

```
UPDATE content_versions SET status = 'SCHEDULED' WHERE id = $1 AND status = 'PUBLISHING'
+ INSERT PublicationAttempt (status = IN_PROGRESS, is_recovery = true)
+ INSERT content_version_transitions (from='PUBLISHING', to='SCHEDULED', actor_type='SYSTEM')
```

All within a single transaction (ADR-002 Invariant 1). If CAS returns 0 rows, the scan exits gracefully — another process has already acted.

**Rule 3 — Resumed Worker Finds CAS-Protected State:**

If a Procrastinate job is re-queued (Rule 1) and the recovering worker resumes execution, it will attempt to call the external publication API. At this point, the entity may be in `PUBLISHING` (worker heartbeat fired, job re-queued before domain scan) or `SCHEDULED` (domain scan fired before heartbeat — should not occur if Rule 1 ordering is maintained, but defensively handled via CAS).

The worker's first action on resumption must be a CAS check:

- If `status = PUBLISHING`: entity is still in-flight. Worker proceeds with external API call.
- If `status != PUBLISHING`: entity was recovered to another state. Worker exits gracefully (CAS returns 0 rows).

**Rule 4 — Operational TTL Definitions (Deferred to Operations Specification):**

The concrete values of `Procrastinate_Heartbeat_TTL`, `Recovery_Scan_Interval`, and `PUBLISHING_TTL` are operational parameters that depend on the acceptable publication stall window and worker restart SLA. These are NOT decided by this ADR. However, the ordering constraint in Rule 1 is an architectural invariant:

```
PUBLISHING_TTL > Procrastinate_Heartbeat_TTL + Recovery_Scan_Interval
```

This constraint must be validated in the Operations Specification before deployment.

**Formally adopted invariant:**

> **Single Recovery Authority Invariant:** Worker liveness recovery and domain-state recovery must not independently re-dispatch the same business operation without CAS-based coordination. The Procrastinate heartbeat mechanism has authority over job liveness. The ADR-002 PUBLISHING recovery scan has authority over domain state. Their interaction is governed by the ordering constraint: PUBLISHING_TTL > Procrastinate_Heartbeat_TTL + Recovery_Scan_Interval.

---

### 8.3 Transactional Outbox Patterns Summary

| Pattern | S3 Eliminated? | Option Compatibility | Additional Cost |
| :--- | :--- | :--- | :--- |
| P3 — PG-Native Job Table (Procrastinate) | ✅ Yes — when Transactional Dispatch Invariant implemented | A only | Application discipline; no relay process |
| P4 — Direct Dispatch + Recovery Scan | ❌ No (detects; does not prevent) | B, C, D, E | Recovery scan implementation; stall window |
| P1 — Transactional Outbox (relay) | ✅ Yes | B, C, D (with relay) | Outbox table + relay process (additional service) |
| P2 — Polling Publisher | ❌ No | All | Stall window = polling interval; duplicate risk |

---

## 9. Retry / Recovery Analysis (Revised — Remediates F-006)

### 9.1 Retry Taxonomy — Full Expansion

Five distinct recovery types must be supported. They are not equivalent and must not be conflated:

| Type | Trigger | Who Owns | Creates New Entity? | CAS Required? |
| :--- | :--- | :--- | :---: | :---: |
| 1. Technical Retry (LLM infra) | Transient LLM HTTP error; no content committed | Framework (queue retry) | ❌ No | ❌ No — same call |
| 2. Technical Retry (Social API infra) | Transient 503/429; PublicationAttempt in-progress | Framework (queue retry) | ❌ No | ❌ No — same attempt |
| 3. Worker Crash Recovery | Procrastinate heartbeat TTL | Procrastinate + CAS | ❌ No | ✅ Yes — re-enters domain state |
| 4. Publication Domain Recovery | ADR-002 PUBLISHING TTL scan | Recovery scan + CAS | ✅ Yes — new PublicationAttempt | ✅ Yes — CAS for transition |
| 5. Editorial Regeneration | Human business decision | Domain use case | ✅ Yes — new ContentVersion | ✅ Yes — CAS on Brief |

**Key distinctions:**

- Types 1 and 2 are framework-level infra retries. They do not touch domain state; the CAS has not yet fired.
- Type 3 is a worker recovery. The CAS has already fired (entity is in an in-flight state). Recovery must re-enter via CAS.
- Type 4 is a domain recovery. It uses the ADR-002 PUBLISHING recovery protocol. It creates a new PublicationAttempt (ADR-002 Invariant 6).
- Type 5 is a business event, not an infra retry. It requires a new ContentVersion (ADR-002 Invariant 4).

### 9.2 Recovery Ownership Matrix

| State Before Recovery | Recovery Owner | Mechanism |
| :--- | :--- | :--- |
| Procrastinate job `doing`, entity `PUBLISHING`, heartbeat active | Procrastinate | Heartbeat timeout → job re-queue |
| Procrastinate job `failed`, entity `PUBLISHING`, TTL exceeded | ADR-002 Domain Scan | CAS PUBLISHING → SCHEDULED + new PublicationAttempt |
| Procrastinate job `failed`, entity `VALIDATED`, no new job | Recovery Scan | Detect stuck entity; re-enqueue GeneratePlatformContent job |
| Entity `SCHEDULED`, no Procrastinate job visible | Recovery Scan | Re-enqueue publication dispatch job |

### 9.3 Recovery Scan Implementation Complexity for Options B, C, D (Remediates F-006)

The original analysis described the recovery scan as "a few SQL queries." A correct implementation is non-trivial:

**Required recovery scan logic (multi-state policy):**

```python
# Simplified pseudo-code — actual implementation is more complex
async def recovery_scan():
    now = datetime.utcnow()

    # 1. Detect ContentVersions in VALIDATED with no pending generation job
    #    Must verify: no Procrastinate/ARQ/Celery job is currently queued for this entity
    #    (Checking job queue from domain layer violates ADR-002 Invariant 7 — must be
    #    done in infrastructure layer; requires cross-layer coordination)
    stuck_validated = await repo.find(status='VALIDATED', no_pending_job=True, older_than=5min)
    for cv in stuck_validated:
        await generate_task.defer(content_version_id=cv.id)  # Risk: duplicate if original job is delayed

    # 2. Detect ContentVersions in SCHEDULED past their scheduled_at with no active publication job
    stuck_scheduled = await repo.find(status='SCHEDULED', scheduled_at_before=now, no_pending_job=True)
    for cv in stuck_scheduled:
        await publish_task.defer(content_version_id=cv.id)  # Same duplicate risk

    # 3. Detect ContentVersions in PUBLISHING beyond PUBLISHING_TTL
    stuck_publishing = await repo.find(status='PUBLISHING', older_than=PUBLISHING_TTL)
    for cv in stuck_publishing:
        # Must use CAS — cannot assume entity is still PUBLISHING
        result = await repo.transition_cas(cv.id, from_status='PUBLISHING', to_status='SCHEDULED')
        if result.rows_affected > 0:
            await repo.create_publication_attempt(cv.id, is_recovery=True)
            await publish_task.defer(content_version_id=cv.id)
        # If CAS fails (0 rows), entity was already recovered by another process — exit gracefully
```

**Complexity factors:**

1. **Detecting "no pending job"** requires querying the job queue from the recovery scan. For Options B/C/D, this means the recovery scan must query both PostgreSQL (domain state) and the external broker (job queue state). This couples the recovery scan to the broker — a cross-infrastructure concern. For Option A, both are in PostgreSQL — a single query suffices.
2. **Duplicate job risk**: If the original job is queued but delayed (queue saturation, worker restart), the recovery scan may enqueue a second job for the same entity. The CAS guard prevents both from completing, but two orphaned job records accumulate.
3. **Multi-state policy**: Each domain state requires a distinct recovery action. This is not a single query.
4. **Testing**: The recovery scan must be tested for each stuck state × each failure mode. This represents a significant test surface.

**Implementation cost estimate:** The recovery scan is a medium-complexity component, not a trivial utility. Its development and testing represents approximately 2–3 days of engineering work (ASSUMPTION — no PRD sprint estimates available). This cost applies to all options except A.

---

## 10. Scheduling Analysis

**F-012 Remediation — Concurrent Periodic Task Safety:**

Procrastinate prevents duplicate periodic task executions through the `procrastinate_periodic_defers` table. When multiple worker instances are running, each checks this table before executing a periodic task. PostgreSQL row-level locking ensures only one worker inserts the deferred periodic task record per scheduled interval. Duplicate periodic task execution is prevented at the database level. (FACT — Procrastinate documentation: "If multiple workers are running, each periodic task will be deferred at most once per schedule.") This is a structural guarantee, not a configuration requirement.

**Scheduling durability comparison:**

| Option | Schedule Location | Durability | Config Required |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | PostgreSQL `procrastinate_jobs.scheduled_at` | Full ACID; same as ADR-002 persistence | None beyond standard PG |
| B — ARQ | Redis sorted set | Configurable; `appendfsync always` for full durability | Explicit Redis config |
| B — TaskIQ | Broker-dependent | Varies | Varies |
| C — Celery | Celery Beat (file or DB) | Moderate; Beat restart required | Beat configuration |
| D — Temporal | Temporal server state | High; Temporal guarantees | Temporal deployment |
| E — App-native | PostgreSQL `ContentVersion.scheduled_at` | Full ACID | Startup scan required |

**Conclusion:** Option A provides the most durable scheduling without additional configuration. Scheduled publication is a PostgreSQL row that participates in all ACID guarantees of the existing database infrastructure. (INFERENCE — consequence of ADR-002 persistence decision)

---

## 11. Concurrency Analysis

The CAS guard is the authoritative concurrency mechanism for all domain state transitions, regardless of worker concurrency model. The queue framework provides worker-level concurrency; CAS provides domain-level mutual exclusion. These are separate concerns. (FACT — ADR-002 §Concurrency Model)

All asyncio-native options (A, B-ARQ, B-TaskIQ, D, E) support `asyncio.gather()` for parallel platform content generation. Celery requires gevent or asyncio pool integration. (FACT)

---

## 12. Operational Analysis (Revised — Remediates F-003, F-004, F-005)

### 12.1 Services and Infrastructure

| Dimension | A (Procrastinate) | B (ARQ) | B (TaskIQ) | C (Celery) | D (Temporal) | E (App-native) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Additional infra services | 0 | 1 | 1 | 2–4 | 2–3 | 0 |
| Local dev containers | 0 extra | 1 extra | 1 extra | 2–4 extra | 2–3 extra | 0 extra |
| Deployment process units | 1 worker | 1 worker + Redis | 1 worker + Redis | 3–4+ | 2–3 + Temporal | Inline with API |

### 12.2 Operational Complexity Summary

**MVP Proportionality:** For a single-newsroom MVP with low article volume, operational simplicity is a high-priority driver. Options C and D require infrastructure that is disproportionate to the MVP workload and team size. Option A and E require no additional services. Options B-ARQ and B-TaskIQ add Redis (+1 service).

### 12.3 Schema Migration Coupling — Procrastinate and Alembic (Remediates F-003)

Procrastinate manages its own schema (4 tables) independently of the application domain schema. This creates a migration coupling risk:

**Risk:** If Procrastinate tables are included in Alembic's `autogenerate`, every Procrastinate version upgrade that modifies its schema will produce Alembic migration scripts in the project's domain migration history. This pollutes the migration lineage with infrastructure changes.

**Mitigation — Required Implementation Constraint:**

Procrastinate tables must be excluded from Alembic's `autogenerate` via the `include_name` callback in `env.py`:

```python
# alembic/env.py — required configuration
PROCRASTINATE_TABLES = {
    "procrastinate_jobs",
    "procrastinate_events", 
    "procrastinate_periodic_defers",
    "procrastinate_versions",
}

def include_name(name, type_, parent_names):
    if type_ == "table":
        return name not in PROCRASTINATE_TABLES
    return True
```

Procrastinate manages its own schema through its own migration mechanism (`procrastinate schema apply` CLI command). Domain migrations (Alembic) and Procrastinate schema updates must be executed independently and in the correct order during deployment. This ordering must be documented in the deployment runbook. (SUPPORTED INFERENCE — standard Procrastinate + Alembic integration pattern; documented in Procrastinate documentation)

**Operational consequence:** Procrastinate upgrades require a separate schema update step in the deployment procedure. This is a manageable operational burden but must be explicitly documented.

### 12.4 PostgreSQL Availability — Coupled Availability Declaration (Remediates F-004)

**Explicit trade-off statement:**

Under Option A, PostgreSQL and the job queue share the same database instance. This creates coupled availability:

```
PostgreSQL unavailable
    → Domain persistence unavailable (expected — all options share this)
    → Transactional job enqueue unavailable
    → Worker job discovery unavailable (LISTEN/NOTIFY halted)
    → Background pipeline halted
```

Under Redis-backed Options B and C, if PostgreSQL becomes temporarily unavailable:

- The Redis job queue remains operational.
- Workers that do not require a domain state write could theoretically continue processing non-blocking jobs.
- New jobs can be enqueued in Redis while PG recovers.

**Assessment for JincSAE MVP:** PostgreSQL unavailability halts all domain operations regardless of queue technology, because every JincSAE use case requires a database read or write. The incremental benefit of queue-availability-without-DB is zero for this system's use cases. All JincSAE jobs require PostgreSQL to function. (SUPPORTED INFERENCE — every use case in the pipeline reads or writes domain state)

**Conclusion:** The coupled availability of Option A is not a material disadvantage for the JincSAE system. The trade-off is accepted as a consequence of the single-database architectural simplicity goal. This must be stated in the decision record so the human decision-maker is informed. It is not a hidden assumption.

### 12.5 Job Table Maintenance — Retention and Pruning (Remediates F-005)

Procrastinate job records accumulate in two tables:

- `procrastinate_jobs`: Job execution records (queued, doing, succeeded, failed).
- `procrastinate_events`: Per-job event history (all state transitions within the job lifecycle).

Without pruning, both tables grow unboundedly. For the MVP workload (low double-digit articles per day, 4–5 jobs per article), growth is approximately 50–100 job records per day. After one year, ~20,000–40,000 records without pruning. At this scale, PostgreSQL VACUUM handles this efficiently and performance impact is negligible. (INFERENCE — based on MVP volume estimate and PostgreSQL MVCC behavior)

**Operational requirement:** A Procrastinate periodic task or scheduled Alembic-triggered cleanup must prune records older than the defined retention period.

**Retention policy ownership (deferred to Operations Specification):**

| Table | Suggested Retention | Reason |
| :--- | :--- | :--- |
| `procrastinate_jobs` (succeeded) | 30 days | Operational lookback window |
| `procrastinate_jobs` (failed) | 90 days | Dead-letter review window |
| `procrastinate_events` | Match associated job retention | No orphan events after job purge |

The concrete retention values are operational parameters. The ADR defines the requirement; the Operations Specification defines the values. Alembic autogenerate must not include Procrastinate table data management (see §12.3).

---

## 13. Reversibility Analysis

The queue library is used in the infrastructure layer only (ADR-002 Invariant 7). The coupling points are limited to:

1. Task definition decorators (`@task`)
2. Dispatch calls (`task.defer_async()`) — infrastructure layer
3. Worker process configuration
4. Periodic task registrations
5. Recovery scan implementations

Switching between Options A, B, and C is a medium-effort infrastructure layer change: task decorators change, dispatch calls change, broker configuration changes. Domain layer unchanged. Use cases unchanged. ADR-002 invariants unchanged. (INFERENCE — consequence of hexagonal architecture)

Switching to Option D (Temporal) is high-effort: Temporal's programming model (deterministic workflow functions, activity patterns) requires significant rearchitecting of the pipeline orchestration code. (INFERENCE — Temporal is a fundamentally different paradigm)

**Note:** Option A is not materially harder to replace than Option B; both are infrastructure concerns. The reversibility cost of A → B is approximately equal to B → A.

---

## 14. Decision Matrix (Revised — Remediates F-009)

| Driver | Weight | A (Procrastinate) | B-ARQ | B-TaskIQ | C (Celery) | D (Temporal) | E (App-native) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1. Operational Simplicity | 3× | **5** | 4 | 4 | 2 | 2 | **5** |
| 2. Python/asyncio Compat. | 3× | **5** | **5** | **5** | 2 | 4 | **5** |
| 3. PG Transaction Integration | 3× | **4** ↓ | 2 | 2 | 2 | **3** ↑ | 3 |
| 4. Crash Recovery | 2× | **5** | 4 | 4 | 4 | **5** | 2 |
| 5. Retry Semantics | 2× | **5** | 2 ↓ | 4 | **5** | **5** | 1 |
| 6. Delayed/Scheduled Exec. | 2× | **5** | 3 ↓ | 4 | 4 | **5** | 3 |
| 7. Idempotent Exec. Support | 2× | 4 | 3 | 4 | 4 | **5** | 2 |
| 8. Observability | 2× | 4 | 3 | 4 | 4 | **5** | 2 |
| 9. Domain Independence | 2× | **5** | **5** | **5** | **5** | **5** | **5** |
| 10. Dev / Testing Complexity | 1× | 4 | 3 | 3 | 3 | 2 | **5** |
| 11. Scalability | 1× | 4 | 4 | 4 | **5** | **5** | 2 |
| 12. Reversibility | 1× | 4 | 4 | 4 | 3 | 2 | **5** |
| 13. Vendor Lock-in | 1× | **5** | 3 | 3 | 3 | 2 | **5** |

**Score changes from original analysis:**

- Driver 3, Option A: 5 → **4** (Transactional integration is achievable but requires implementation discipline; not automatic. F-001 remediation.)
- Driver 3, Option D: 2 → **3** (Pattern D2 makes transactional integration achievable by design; F-009 remediation.)
- Driver 5, Option B-ARQ: 3 → **2** (No built-in dead-letter; no native backoff jitter; Constitution §15 tension. F-008 remediation.)
- Driver 6, Option B-ARQ: 4 → **3** (Redis durability risk for scheduled jobs; `appendfsync always` required for full schedule durability. F-002/S7 remediation.)

### Weighted Scores (Revised)

| Option | Critical (3×) | High (2×) | Medium (1×) | **Total** |
| :--- | :---: | :---: | :---: | :---: |
| A — Procrastinate | (5+5+4)×3 = **42** | (5+5+5+4+4+5)×2 = **56** | (4+4+4+5)×1 = **17** | **115** |
| B — ARQ | (4+5+2)×3 = **33** | (4+2+3+3+3+5)×2 = **40** | (3+4+4+3)×1 = **14** | **87** |
| B — TaskIQ | (4+5+2)×3 = **33** | (4+4+4+4+4+5)×2 = **50** | (3+4+4+3)×1 = **14** | **97** |
| C — Celery | (2+2+2)×3 = **18** | (4+5+4+4+4+5)×2 = **52** | (3+5+3+3)×1 = **14** | **84** |
| D — Temporal | (2+4+3)×3 = **27** | (5+5+5+5+5+5)×2 = **60** | (2+5+2+2)×1 = **11** | **98** |
| E — App-native | (5+5+3)×3 = **39** | (2+1+3+2+2+5)×2 = **30** | (5+2+5+5)×1 = **17** | **86** |

**Note on Driver 9 (F-011 remediation):** All options score 5 on Domain Independence. This reflects a quality floor requirement, not a differentiator. All options are equally strong on this dimension if hexagonal architecture is respected. The equal scores do not affect relative ranking.

Option A (Procrastinate) remains the highest-scoring candidate (115, revised from 118). The revised score on Driver 3 (4 instead of 5) is the only change to Option A's score, reflecting the F-001 remediation. Temporal rises to 98 (from 95) due to Driver 3 correction (3 instead of 2). ARQ drops to 87 (from 92) due to retry and scheduling revisions.

---

## 15. Formally Adopted Architectural Invariants

The following invariants are proposed for adoption by ADR-003. They must survive the Red Team before formal acceptance.

### Invariant ADR-003-I1 — Transactional Dispatch Invariant

> A domain state transition that requires asynchronous execution must not commit without its corresponding job being transactionally registered in the same PostgreSQL transaction. Under Option A, the `defer_async()` call must execute within the same `session.begin()` context as the CAS UPDATE and audit INSERT.

### Invariant ADR-003-I2 — Single Recovery Authority Invariant

> Worker liveness recovery and domain-state recovery must not independently re-dispatch the same business operation without CAS-based coordination. The ordering constraint must be maintained: `PUBLISHING_TTL > Procrastinate_Heartbeat_TTL + Recovery_Scan_Interval`.

### Invariant ADR-003-I3 — CAS Recovery Invariant

> Every recovery transition — whether triggered by worker recovery, the PUBLISHING scan, or the general stuck-entity scan — must use the same conditional state-transition mechanism defined by ADR-002: `UPDATE ... WHERE status = 'CURRENT'`. A recovery transition that finds `rows_affected = 0` must exit gracefully. No recovery mechanism may bypass the CAS guard.

### Invariant ADR-003-I4 — Retry Type Segregation Invariant

> Framework-level technical retries (infra errors before domain state commit) must not be conflated with domain-level recovery operations (after domain state has been committed). Technical retries are queue framework concerns. Domain recovery operations must use CAS and create new domain entities as required by ADR-002 Invariants 4, 5, and 6.

---

## 16. Preliminary Recommendation (Revised)

### Recommended Option: A — Procrastinate (PostgreSQL-Native Queue)

**Primary reason (corrected):** Option A is the only candidate that can structurally prevent Scenario S3 (Lost Dispatch) through the Transactional Dispatch Invariant. This prevention is achievable — not automatic — and requires correct implementation at the application layer. Provided the invariant is implemented, Option A gives the JincSAE the strongest guarantee that no domain state transition is silently lost without a corresponding asynchronous job.

**Secondary reasons:**

- Zero additional infrastructure services (PostgreSQL already required by ADR-002).
- Native asyncio support with `async def` job functions sharing the SQLAlchemy async session context.
- Built-in retry with exponential backoff and jitter (`RetryStrategy`).
- PostgreSQL-backed delayed/scheduled jobs with full ACID durability — no additional Redis durability configuration required.
- Concurrent periodic task safety guaranteed by `procrastinate_periodic_defers` table locking.
- Failed jobs observable as SQL queries on the same database used for domain queries.
- Single Recovery Authority Protocol (§8.2) provides a coherent crash recovery model for publication jobs.

**Rejected options (revised rationale):**

| Option | Primary Rejection Reason (Revised) |
| :--- | :--- |
| B — ARQ | S3 risk (no transactional enqueue); no built-in dead-letter (Constitution §15 tension); Redis durability configuration required for schedule safety; no native exponential backoff with jitter |
| B — TaskIQ | S3 risk; +1 infrastructure service (Redis); weaker than Procrastinate on Driver 3 |
| C — Celery | **Primary: Driver 3** — cannot participate in PostgreSQL transactions; **Secondary: Driver 1** — 2–4 additional infrastructure services disproportionate to MVP. asyncio is a secondary concern. |
| D — Temporal | MVP complexity disproportionate to workload; 2–3 additional services; Pattern D2 is achievable but requires significant team investment; dual-authority risk manageable but adds architectural discipline burden not justified by PRD scope |
| E — App-native | No built-in retry semantics; no dead-letter; no formal scheduling; explicit failure threshold defined in §5.5; inadequate as production queue strategy |
| B — RQ | Eliminated — synchronous workers incompatible with asyncio architecture (ADR-001) |

**Conditions that would change the recommendation:**

1. If article volume grows to hundreds per day and PG job table contention becomes measurable → migrate to TaskIQ (B-TaskIQ) with a recovery scan.
2. If Redis is introduced for another reason (caching, sessions) → re-evaluate Option B with reduced marginal operational cost.
3. If Procrastinate maintenance is abandoned → migrate to TaskIQ (compatible interface concepts, medium migration effort).
4. If the system evolves to multi-step sagas with complex branching → evaluate Temporal for those specific workflow modules.

---

## 17. Risks

| Risk | Severity | Option | Mitigation |
| :--- | :--- | :--- | :--- |
| Transactional Dispatch Invariant violated in implementation | High | A | Code review gate; integration test verifying rollback propagation |
| Dual recovery path race (PUBLISHING TTL vs. heartbeat TTL) | High | A | Single Recovery Authority Protocol (§8.2); TTL ordering constraint |
| PG job table contention at scale | Low (MVP) | A | Per-queue concurrency limits; migration path to TaskIQ exists |
| Alembic autogenerate contamination | Medium | A | Explicit `include_name` exclusion in `env.py` (§12.3) |
| ARQ Redis durability failure on scheduler crash | Medium | B-ARQ | `appendfsync always` configuration; or use Option A |
| Recovery scan duplicate job accumulation (Options B/C/D) | Medium | B, C, D | CAS guard prevents dual completion; monitoring cleanup required |
| Celery asyncio support regression | Low (Celery rejected) | C | N/A — Celery rejected on Driver 3 grounds |
| Temporal state divergence from PostgreSQL | Medium (if D chosen) | D | Pattern D2 discipline; extensive integration testing |
| Procrastinate community maintenance abandonment | Low | A | Medium migration effort; TaskIQ as documented successor path |

---

## 18. Unknowns

| Unknown | Impact | Required Before |
| :--- | :--- | :--- |
| Article publication volume target | Determines long-term PG job table scalability adequacy | Not blocking for MVP |
| Operations team capacity for infrastructure management | Affects Option B operational complexity scoring | Not blocking — scored conservatively |
| Deployment environment (cloud provider) | Managed Redis may reduce Option B operational burden | Infrastructure ADR |
| Future Redis requirement from other ADRs | May reduce marginal cost of Option B | Not blocking |
| Procrastinate SQLAlchemy async connection sharing — production verification | Confirms F-001 integration pattern is correct in production | Required before architectural acceptance |

---

## 19. Evidence Gaps

| Gap | Classification | Recommendation |
| :--- | :--- | :--- |
| Procrastinate + SQLAlchemy async session sharing in production environments | INFERENCE from documentation | Verify with integration test before Architecture Review acceptance |
| ARQ retry storm behavior under sustained failure | UNKNOWN | Not blocking — ARQ is second-ranked option |
| Celery 5.x current asyncio pool stability | INFERENCE — version-dependent | Not blocking — Celery rejected on Driver 3 grounds |
| Temporal Python SDK production stability rating | INFERENCE | Not blocking — Temporal rejected on proportionality grounds |

---

## 20. Red Team Attack Surface (Revised)

The following claims are the most vulnerable to adversarial challenge. The Red Team should focus attacks here:

| Claim | Vulnerability | Potential Falsification |
| :--- | :--- | :--- |
| "Transactional Dispatch Invariant is implementable correctly with Procrastinate + SQLAlchemy async" | Requires specific connection-sharing pattern not trivially achieved | Demonstrate a production code path where the job INSERT uses a separate connection despite following documented integration patterns |
| "PUBLISHING_TTL > Heartbeat_TTL + Scan_Interval eliminates the dual recovery race" | Assumes both TTLs are correctly configured and respected; assumes no clock skew between workers | Construct a scenario where both recovery mechanisms fire simultaneously despite the TTL ordering constraint |
| "PG job table contention is not a concern at MVP scale" | Volume is inferred, not specified in PRD | If PRD is updated with high-volume requirement, contention must be re-evaluated |
| "Celery is correctly rejected on Driver 3 grounds" | Celery could use a PostgreSQL result backend + outbox pattern to approximate transactional integration | Design a Celery + PG outbox that achieves Driver 3 parity with Procrastinate; evaluate if this changes the recommendation |
| "Option E is inadequate above the defined threshold" | Threshold is partially qualitative | Define a concrete scenario where E fails but A succeeds at MVP scale |
| "Temporal's dual-authority concern is resolved by Pattern D2" | Pattern D2 requires architectural discipline at every Activity boundary | Identify a realistic code path where Temporal activity state and PostgreSQL domain state diverge |

---

*This document is a REVISED ANALYSIS artifact following Architecture Review remediation. Status: `PROPOSED — UNDER ARCHITECTURAL REVIEW`. The next phase is an independent adversarial ADR-003 Red Team Review. This document does not make a final human decision. It does not mark ADR-003 as Accepted.*

---

## Final Quality Gate — Self-Assessment

| Check | Status |
| :--- | :--- |
| F-001 explicitly remediated: "structurally impossible" removed | ✅ §8.1 |
| F-002 has one coherent recovery protocol | ✅ §8.2 Single Recovery Authority Protocol |
| No "structurally impossible" claim without proof | ✅ Removed and replaced with invariant language |
| CAS remains consistent with ADR-002 | ✅ §8.1, §8.2, §9.2, Invariant I3 |
| Transaction boundaries are explicit | ✅ §8.1 Conditions 1–4 |
| Worker recovery and domain recovery do not race | ✅ §8.2 Rule 1, Rule 2, Rule 3 |
| PostgreSQL availability trade-off declared | ✅ §12.4 |
| Job retention/pruning ownership identified | ✅ §12.5 |
| Celery rejection rationale corrected | ✅ §5.3 — Driver 3 primary, asyncio secondary |
| No premature human decision made | ✅ Status remains PROPOSED — UNDER ARCHITECTURAL REVIEW |
