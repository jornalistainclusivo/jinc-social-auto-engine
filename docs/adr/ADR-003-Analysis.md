---
adr-id: ADR-003
title: "Async Processing, Background Jobs & Workflow Execution — Analysis"
status: PROPOSED FOR ARCHITECTURE REVIEW
phase: Analysis
authority-chain:
  - docs/ENGINEERING_CONSTITUTION.md
  - docs/PRD.md
  - docs/SDD.md
  - docs/adr/ADR-001-Runtime-Language.md
  - docs/adr/ADR-002-Persistence-Strategy.md
  - docs/adr/MASTER_BRIEFING_ADR-003_ASYNC_PROCESSING.md
created-at: 2026-08-31
---

# ADR-003 Analysis

# Async Processing, Background Jobs & Workflow Execution

---

## 1. Executive Summary

The JincSAE requires an asynchronous execution layer to drive a multi-stage, LLM-assisted editorial pipeline from article ingestion through publication to external social media platforms. This analysis evaluates five candidate strategies across 13 non-overlapping decision drivers, 8 explicit failure scenarios, and 4 transactional consistency patterns.

**The central architectural question of this ADR is not throughput or ecosystem familiarity. It is:**

> How can a committed domain state transition reliably cause asynchronous downstream work without creating a dual-write inconsistency between PostgreSQL state and the job queue?

This question — the Lost Dispatch Problem (Scenario S3) — is the primary differentiator between the five candidates. Its resolution depends directly on ADR-002's architectural invariants, particularly Invariant 1 (atomic transaction boundary) and the principle that PostgreSQL is the authoritative source of domain state.

**Preliminary Recommendation:** Option A (Procrastinate — PostgreSQL-native queue) as the primary evaluation candidate, pending Architecture Review and Red Team. Option A is the only candidate that structurally eliminates Scenario S3 by making job enqueue part of the PostgreSQL transaction, at zero additional infrastructure cost. This recommendation is provisional. It must be contested by the Architecture Review and Red Team before human decision.

**Status:** `PROPOSED FOR ARCHITECTURE REVIEW`

This document does not accept ADR-003. It does not make a final decision.

---

## 2. Decision Context

### 2.1 System Nature

The JincSAE is a Python-based (ADR-001: Accepted) editorial automation engine. Its pipeline is inherently asynchronous: article analysis, LLM generation calls, content validation, and social platform publication all involve I/O operations with unpredictable latency (LLMs: seconds to minutes; social APIs: milliseconds to seconds; platform rate limits: variable).

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
    → SCHEDULED state
    → PUBLISHING state
    → External platform API call (non-transactional, residual risk accepted)
    → PUBLISHED or PUBLISH_FAILED
    → Recovery scan (periodic, TTL-based)
```

### 2.2 Workload Characterization (from PRD)

The PRD does not specify a target article volume, concurrent user count, or jobs-per-second requirement. (FACT: PRD examined; no volume SLA defined)

**Conservative MVP estimate based on PRD scope:** A single journalistic newsroom, small editorial team. (INFERENCE: based on PRD product vision — single publication, not multi-tenant SaaS at launch)

Assumed workload profile:

- Articles per day: low double digits (ASSUMPTION: typical single-newsroom publication cadence)
- Platforms per article: 4 (LinkedIn, Facebook, Instagram, Bluesky) = 4 generation jobs per article
- Concurrent LLM calls: low single digits
- Peak publication jobs: low tens per day
- Recovery scans: periodic, minutes interval

**Conclusion:** The JincSAE MVP does not require high-throughput queue infrastructure. Throughput is not a primary decision driver. (INFERENCE from PRD workload estimate)

### 2.3 Accepted Constraints from ADR-001 and ADR-002

These are non-negotiable. See §3 for full detail.

---

## 3. Locked Constraints (Non-Negotiable)

### 3.1 From ADR-001 — Python Runtime

- All async options must be Python-compatible. (FACT)
- asyncio is the preferred I/O model for the Python async ecosystem (FastAPI, SQLAlchemy async, asyncpg). (FACT)
- Node.js-native solutions (BullMQ) are excluded. (FACT — ADR-001 determines the runtime)

### 3.2 From ADR-002 — PostgreSQL + Hybrid Audit (7 Invariants)

| # | Invariant | Impact on ADR-003 |
| :--- | :--- | :--- |
| 1 | CAS UPDATE + audit INSERT in one explicit DB transaction | Workers executing state transitions must do so atomically; job dispatch must not split the transaction |
| 2 | Audit history is append-only | Workers must INSERT new rows; never UPDATE existing audit records |
| 3 | Audited entities use soft-delete | Workers must not hard-delete entities with audit chains |
| 4 | Regeneration creates a new ContentVersion | A "retry generation" job must create a new ContentVersion; it cannot overwrite the existing one |
| 5 | PublicationAttempt is immutable | Workers do not modify status of existing PublicationAttempt rows once created |
| 6 | Retry = new PublicationAttempt record | Each retry attempt creates a new PublicationAttempt INSERT; workers do not UPDATE to retry |
| 7 | Domain layer must not import queue infrastructure | Queue libraries live in the infrastructure layer; domain is queue-agnostic |

### 3.3 Core Principle (from Briefing)

> **The async/job system executes work. PostgreSQL remains the authoritative source of domain state.**

Workers may fail, restart, or be duplicated. Correctness must depend on:

- persisted state (PostgreSQL)
- transaction boundaries (ADR-002 Invariant 1)
- CAS concurrency guards (ADR-002 §Concurrency Model)
- idempotent use cases
- explicit retry policies

The queue must never become the source of truth.

---

## 4. Decision Drivers

The following 13 drivers are non-overlapping. Each covers a distinct concern.

| # | Driver | Weight | Definition |
| :--- | :--- | :---: | :--- |
| 1 | Operational Simplicity | Critical (3×) | Count of distinct infrastructure services required beyond PostgreSQL (already accepted) |
| 2 | Python & asyncio Compatibility | Critical (3×) | Native asyncio support; `async def` jobs; no thread-pool workaround required |
| 3 | PostgreSQL Transaction Integration | Critical (3×) | Ability to enqueue jobs within a PostgreSQL transaction; structural resolution of Scenario S3 |
| 4 | Crash Recovery | High (2×) | Job recoverability when worker crashes mid-execution; no permanent job loss |
| 5 | Retry Semantics | High (2×) | At-least-once delivery; exponential backoff with jitter; max retry limit; dead-letter routing |
| 6 | Delayed & Scheduled Execution | High (2×) | Native enqueue with future datetime; required for scheduled publication |
| 7 | Idempotent Execution Support | High (2×) | Framework support for duplicate delivery safety; CAS compatibility |
| 8 | Observability | High (2×) | Job status visibility; failure logs; queue depth; worker health |
| 9 | Domain Independence | High (2×) | Queue library confined to infrastructure layer; domain does not import queue primitives |
| 10 | Development & Testing Complexity | Medium (1×) | Local setup overhead; unit testability of jobs without broker infrastructure |
| 11 | Scalability | Medium (1×) | Suitability from MVP to small newsroom scale without architectural change |
| 12 | Reversibility | Medium (1×) | Migration cost if the option needs to be replaced |
| 13 | Vendor/Infrastructure Lock-in | Medium (1×) | Dependency on proprietary services or cloud-specific features |

**Prohibited drivers:** popularity, team familiarity, industry standard status.

---

## 5. Candidate Strategies

### Option A — Procrastinate (PostgreSQL-Native Queue)

**Description:** Procrastinate is a Python asyncio-native task queue that uses PostgreSQL as the job broker. Jobs are rows in PostgreSQL tables. Workers poll the job table using PostgreSQL's `LISTEN/NOTIFY` for efficient push-based wake-up, falling back to periodic polling.

**Key architectural property:** Jobs can be enqueued within the same SQLAlchemy database session (and therefore the same transaction) as the domain state change. This is the critical property that structurally eliminates the Lost Dispatch Problem (Scenario S3). (FACT — Procrastinate documentation explicitly supports this pattern via `procrastinate.SyncPgConnector` and async variants)

**Infrastructure dependencies:** PostgreSQL (already accepted in ADR-002). No additional service required. (FACT)

**asyncio support:** Native asyncio worker; `async def` task functions supported. (FACT)

**Delayed/scheduled execution:** Native `schedule_in` and `schedule_at` parameters on task dispatch. (FACT)

**Retry semantics:** Configurable per-task retry strategy including max retries, retry delays, and exponential backoff with jitter via `RetryStrategy`. (FACT)

**Schema impact:** Adds approximately 3–4 tables to the PostgreSQL schema (`procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`, `procrastinate_versions`). These live alongside domain tables in the same database. (FACT)

**Maturity:** Actively maintained; v2.x as of 2024; production usage documented. (FACT)

**FastAPI integration:** Documented integration patterns; lifecycle managed via FastAPI lifespan events. (FACT)

**Limitations:**

- Worker scalability depends on PostgreSQL connection count. Under high job volume, the job table can become a hotspot. (INFERENCE — relevant only at high job volumes not evidenced in MVP PRD)
- Single infrastructure service but no physical separation between application DB and job queue. (FACT — can be mitigated by a dedicated PostgreSQL schema if needed)
- Community smaller than Celery. (FACT)

---

### Option B — Redis-Backed Async Python Queue

**Sub-candidates evaluated:**

#### B1 — ARQ (asyncio Redis Queue)

ARQ is an asyncio-native, Redis-backed task queue designed for simplicity. Workers are `async def` functions; the library is minimal.

**asyncio support:** Native; `async def` job functions; no thread wrapping. (FACT)
**Redis requirement:** Redis 5.0+ (FACT). Adds one infrastructure service beyond PostgreSQL.
**Delayed execution:** Supported natively via `defer_by` / `defer_until`. (FACT)
**Retry semantics:** Basic; configurable max_tries; no built-in exponential backoff with jitter — must be implemented manually. (FACT — ARQ docs confirm simple retry without built-in backoff strategy)
**Schema impact:** None in PostgreSQL. Job state lives in Redis.
**Scheduled periodic tasks:** Supported via cron-style periodic tasks. (FACT)
**Crash recovery:** If a worker crashes, ARQ uses a health-check mechanism; jobs in-flight may be requeued after a configurable timeout. (FACT — but recovery depends on Redis durability configuration)
**Redis durability:** With Redis `appendfsync always`, data loss on crash is minimal but not zero. With default `everysec`, up to 1 second of jobs could be lost. (FACT — Redis persistence documentation)

#### B2 — TaskIQ

TaskIQ is a modern asyncio-native task queue with pluggable brokers (Redis, NATS, RabbitMQ, in-memory, and others).

**asyncio support:** Native. (FACT)
**Broker flexibility:** Pluggable — could use Redis for MVP, different broker later. (FACT)
**Middleware support:** Pre/post-execution middleware for logging, metrics. (FACT)
**Retry semantics:** Built-in retry with configurable backoff. (FACT)
**Maturity:** Newer library; smaller community than Celery or RQ. (FACT)
**Delayed execution:** Supported; broker-dependent. (FACT)

#### B3 — RQ (Redis Queue)

RQ is a simple Redis-backed Python task queue. Workers are synchronous Python functions.

**asyncio support:** Not native. Async jobs require `asyncio.run()` inside sync worker functions, which creates a new event loop per job. Not compatible with a shared async SQLAlchemy session across jobs. (FACT — RQ documentation; RQ workers are synchronous processes)
**Conclusion for JincSAE:** RQ is **incompatible** with the JincSAE async architecture (FastAPI + SQLAlchemy async + asyncpg). Running `asyncio.run()` inside an RQ worker is architecturally incorrect; it creates resource waste and cannot share a database connection pool. (INFERENCE from architecture requirements)

**RQ is eliminated from further analysis.** It is retained in the comparison matrix as an eliminated option for transparency.

**Option B summary for analysis:** ARQ (B1) and TaskIQ (B2) are the viable sub-options. Both require Redis as an additional infrastructure service. ARQ is more mature for pure asyncio patterns; TaskIQ provides more framework structure.

---

### Option C — Celery

Celery is the most widely adopted Python background task framework.

**asyncio support:** Celery 5.x has begun adding asyncio support, but it is not fully production-stable as of the analysis period. The primary Celery worker model is synchronous (prefork or gevent workers). Running async code in Celery requires `asyncio.run()` or a `gevent`-patched environment. (FACT — Celery 5.x asyncio support is experimental/partial; Celery GitHub and documentation confirm this as of 2024)

**Infrastructure dependencies:** Requires a message broker (RabbitMQ or Redis) and optionally a result backend (Redis, PostgreSQL, or other). Minimum: 2 additional services. (FACT)

**Retry semantics:** Mature retry support; `autoretry_for`, `max_retries`, `countdown`, and `bind=True` patterns. (FACT)

**Delayed execution:** Supported via `eta` and `countdown`. (FACT)

**Scheduled tasks:** Celery Beat is a separate scheduler process. Adds a third deployment unit. (FACT)

**Observability:** Flower is the standard monitoring UI, requiring a fourth deployment unit for visibility. (FACT)

**Transaction integration:** Celery does not participate in database transactions. Enqueuing a Celery task after a DB commit is the standard pattern — this means Scenario S3 (DB commits, task dispatch fails) is a real risk with no structural mitigation in Celery itself. (FACT)

**Dual-write problem:** Celery has no mechanism to atomically enqueue a task within a database transaction. The standard pattern is `task.apply_async()` after `db.commit()` — creating a non-atomic dual-write. (FACT)

**Known failure modes:** Celery's at-least-once semantics require idempotent tasks; duplicate delivery is possible. (FACT — documented Celery behavior) Task results stored in result backends can cause memory growth. (KNOWN ISSUE — Celery documentation)

**Maturity:** Celery is mature and battle-tested at scale. (FACT)

**Assessment:** Celery's combination of incomplete asyncio support, 2–4 required infrastructure services, and structural inability to enqueue within a database transaction makes it a poor fit for the JincSAE MVP. Its scale advantages are irrelevant at the MVP workload volume.

---

### Option D — Temporal (Durable Workflow Engine)

Temporal is a distributed, durable workflow orchestration platform. Workflows are defined as code; the Temporal server persists workflow state in its own store.

**Infrastructure dependencies:** Temporal Server (separate process); its own persistence store (Cassandra or PostgreSQL, but separate from the application's PostgreSQL); a Temporal Web UI. Minimum: 2–3 additional services. (FACT — Temporal deployment documentation)

**Python SDK:** `temporalio` Python SDK is available and actively maintained. Supports asyncio natively. (FACT)

**Durability model:** Temporal persists workflow execution state independently of the application database. A workflow can survive worker crashes without any application-level recovery code. (FACT)

**State ownership conflict:** Temporal maintains its own authoritative state for workflow progress. The JincSAE architecture (ADR-002) mandates that PostgreSQL is the authoritative source of domain state. Running domain state transitions through Temporal creates a second authoritative state store in conflict with ADR-002's principle. (INFERENCE — architectural analysis)

If Temporal owns the workflow state, then:

- The CAS guard in PostgreSQL and the Temporal workflow state must be kept synchronized.
- Two systems claim authority over the same domain transitions.
- This creates a dual-authority problem, not a dual-write problem.

This is not a fatal argument against Temporal — the workflow could be designed so that Temporal orchestrates calls to application use cases that perform CAS transitions in PostgreSQL. However, this requires careful architectural discipline to avoid state divergence.

**PostgreSQL transaction integration:** Temporal does not participate in PostgreSQL transactions. Enqueuing a Temporal workflow signal from within a PostgreSQL transaction creates the same Scenario S3 risk as Celery and Redis-backed options. (FACT — Temporal's interaction model does not support transactional integration with external databases)

**Development complexity:** Temporal's programming model (deterministic workflow code, activity functions, signal handling) is conceptually different from a simple job queue. Learning curve is significant. (INFERENCE from Temporal documentation and community feedback)

**MVP proportionality test:** Temporal's primary value is in long-running, durable workflows with complex branching, human-in-the-loop wait states, and saga orchestration. The JincSAE pipeline does contain these elements — particularly the unbounded human approval wait. However, these can be modeled through PostgreSQL state alone: the worker simply stops when a ContentVersion reaches `PENDING_REVIEW`, and a new job is dispatched when approval happens. Temporal's durability adds no material value over PostgreSQL state persistence for this pattern at MVP scale. (INFERENCE)

**Verdict:** Temporal fails the MVP proportionality test. Its infrastructure complexity is unjustified given the workload and the fact that PostgreSQL already provides durable state. It remains a valid future evolution option if the system grows to multi-step sagas across many external services.

---

### Option E — Application-Native Scheduling (Minimal Infrastructure)

**Description:** Use FastAPI background tasks or a simple `asyncio` task loop within the application process, plus periodic polling of PostgreSQL for pending work.

**How it works:**

- `BackgroundTasks` in FastAPI for lightweight post-request processing.
- An asyncio `while True` polling loop within the same process for pipeline continuation and publication scheduling.
- No separate worker process; no external broker.

**Infrastructure dependencies:** None beyond PostgreSQL. (FACT)

**asyncio support:** Native — all code runs in the same event loop. (FACT)

**Failure modes:**

- If the FastAPI process crashes, all in-flight background tasks are lost immediately. There is no recovery mechanism unless PostgreSQL state is used to re-discover pending work at next startup. (FACT)
- This requires all intermediate pipeline states to be persisted before any async handoff — which is exactly what ADR-002 mandates. So recovery is possible in principle, but only if the polling loop actively re-scans for stuck entities on startup.
- The polling loop is the recovery mechanism. Maximum stall time = polling interval.

**Scheduled execution:** A polling loop can approximate scheduling by checking `scheduled_at <= now()` in PostgreSQL. This is sufficient for minute-level precision. (INFERENCE)

**Retry semantics:** Must be implemented entirely by the application. No built-in backoff, jitter, or dead-letter. (FACT — there is no framework here)

**Concurrency:** Multiple simultaneous LLM calls can be executed with `asyncio.gather()`. However, if the FastAPI process is under load, background tasks may be starved. Separating the worker process from the API process is a standard operational best practice. (INFERENCE)

**Scale limit:** This approach does not scale beyond a single process. Adding a second API instance creates two competing polling loops, requiring CAS to prevent duplicate execution (which it does — ADR-002 Invariant 6). However, managing multiple competing pollers increases operational complexity without the framework support of a proper queue. (INFERENCE)

**Assessment:** Option E is a viable, zero-infrastructure starting point but requires significant application-level investment to implement retry semantics, scheduling, and recovery that proper queue frameworks provide as built-in features. It is an anti-pattern for production systems beyond very small scale or very short MVP windows. However, for an initial prototype phase or if the queue is to be introduced incrementally, it is a legitimate evaluation option.

---

## 6. Comparative Analysis

### 6.1 PostgreSQL Transaction Integration (Critical Driver)

This is the single most important differentiator for the JincSAE architecture.

| Option | Can Enqueue Within PostgreSQL Transaction? | S3 Risk |
| :--- | :--- | :--- |
| A — Procrastinate | ✅ YES — jobs are PostgreSQL INSERTs in the same transaction | Structurally eliminated |
| B — ARQ / TaskIQ | ❌ NO — Redis write is external; cannot share PG transaction | Exists; needs recovery scan |
| C — Celery | ❌ NO — broker write is external | Exists; needs recovery scan |
| D — Temporal | ❌ NO — Temporal server is external | Exists; needs recovery scan |
| E — App-native | ✅ Partial — in-process dispatch can follow DB commit atomically within same asyncio task | Reduced but not eliminated without careful design |

(FACT for Procrastinate; FACT for Redis/Celery/Temporal external write; INFERENCE for E)

**Consequence:** Options B, C, and D all require a compensating recovery mechanism (polling scan) to detect entities that are in a valid state but have no pending job. Only Option A and a carefully designed Option E eliminate this structurally.

### 6.2 Infrastructure Services Required

| Option | Additional Services | Local Dev Services |
| :--- | :--- | :--- |
| A — Procrastinate | 0 (PostgreSQL already required) | 0 additional |
| B — ARQ | 1 (Redis) | 1 (Redis container) |
| B — TaskIQ | 1 (Redis, default) | 1 (Redis container) |
| C — Celery | 2–4 (broker + result backend + Beat + Flower) | 2–4 additional |
| D — Temporal | 2–3 (Temporal server + its DB + Web UI) | 2–3 additional |
| E — App-native | 0 | 0 |

(FACT for all — based on documented deployment requirements)

### 6.3 asyncio Compatibility

| Option | Native asyncio | Async def jobs | Assessment |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ Full | ✅ Yes | Excellent |
| B — ARQ | ✅ Full | ✅ Yes | Excellent |
| B — TaskIQ | ✅ Full | ✅ Yes | Excellent |
| B — RQ | ❌ No | ❌ No | Eliminated |
| C — Celery | ⚠️ Partial (5.x experimental) | ⚠️ Workaround needed | Problematic |
| D — Temporal | ✅ Full | ✅ Yes | Good |
| E — App-native | ✅ Full | ✅ Yes | Excellent |

(FACT for Procrastinate, ARQ, TaskIQ native async; FACT for Celery partial; FACT for Temporal Python SDK async)

### 6.4 Delayed & Scheduled Execution

| Option | Delayed Jobs | Scheduled (Periodic) | Future Datetime |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ `schedule_at` | ✅ Periodic tasks | ✅ Yes |
| B — ARQ | ✅ `defer_until` | ✅ Cron tasks | ✅ Yes |
| B — TaskIQ | ✅ Yes | ✅ Cron | ✅ Yes |
| C — Celery | ✅ `eta` | ✅ Celery Beat (separate process) | ✅ Yes |
| D — Temporal | ✅ Timers | ✅ Schedules | ✅ Yes |
| E — App-native | ⚠️ Polling-based approximation | ⚠️ asyncio loop | ⚠️ Minute-level precision only |

(FACT for all documented frameworks; INFERENCE for E precision limitation)

### 6.5 Retry Semantics

| Option | Backoff | Jitter | Max Retries | Dead Letter |
| :--- | :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ Built-in RetryStrategy | ✅ Yes | ✅ Yes | ✅ Failed status in PG table |
| B — ARQ | ⚠️ Manual | ❌ Manual | ✅ max_tries | ⚠️ No native DLQ |
| B — TaskIQ | ✅ Built-in | ✅ Yes | ✅ Yes | ✅ Configurable |
| C — Celery | ✅ Mature | ✅ Yes | ✅ Yes | ✅ Yes |
| D — Temporal | ✅ Native | ✅ Yes | ✅ Yes | ✅ Workflow failure state |
| E — App-native | ❌ Custom | ❌ Custom | ❌ Custom | ❌ Custom |

(FACT for Procrastinate, Celery, Temporal; FACT for ARQ limited backoff; INFERENCE for E requiring full custom implementation)

### 6.6 Observability

| Option | Built-in Monitoring | Log Integration | Queue Depth Visibility |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ Django Admin / custom query | ✅ Structured events table | ✅ SQL query on PG table |
| B — ARQ | ⚠️ Basic CLI | ✅ Python logging | ⚠️ Redis key inspection |
| B — TaskIQ | ✅ Middleware-based | ✅ Yes | ✅ Broker-dependent |
| C — Celery | ✅ Flower (separate service) | ✅ Yes | ✅ Flower / Celery Inspect |
| D — Temporal | ✅ Temporal Web UI | ✅ Yes | ✅ Rich workflow visibility |
| E — App-native | ❌ Custom required | ✅ Python logging | ❌ Custom required |

(FACT for all framework-provided features; observability noted as strong Temporal differentiator)

---

## 7. Failure-Mode Analysis

### Scenario S1 — Worker Crash After Job Claim

| Option | Detection Mechanism | Recovery | Automatic? |
| :--- | :--- | :--- | :--- |
| A — Procrastinate | PG job record status `doing`; heartbeat TTL | Worker restart queries for stuck `doing` jobs | ✅ Automatic |
| B — ARQ | Redis job key with visibility timeout | ARQ health check requeues after timeout | ✅ Automatic (Redis-dependent) |
| B — TaskIQ | Broker-dependent visibility timeout | Requeued after ACK timeout | ✅ Automatic |
| C — Celery | Broker visibility timeout (acks_late) | Requeued after visibility timeout | ✅ Automatic |
| D — Temporal | Temporal server detects worker disconnect | Workflow activity retried automatically | ✅ Automatic |
| E — App-native | None — process crash = job loss | Startup polling scan re-discovers stuck entities | ⚠️ On next restart only |

**Assessment:** All options except E provide automatic crash recovery. Option A's recovery is PG-native: a `doing` job beyond its heartbeat TTL is automatically reclaimed. Options B/C/D depend on broker visibility timeouts. Option E requires a startup scan — acceptable only if startup is fast and downtime is short. (FACT for A, B, C, D mechanisms; INFERENCE for E limitation)

---

### Scenario S2 — Duplicate Execution

All options deliver at-least-once semantics. Duplicate execution is possible in all cases. The JincSAE defense is application-level, not framework-level:

- **ADR-002 CAS guard:** `UPDATE ... WHERE status = 'X'` ensures only one actor can perform a given state transition. If a duplicate job executes, the CAS returns 0 rows and the job exits without harm. (FACT — ADR-002 §Concurrency Model)
- **ADR-002 Invariant 4:** A "retry generation" duplicate creates a new ContentVersion but the CAS guard on the Brief prevents two simultaneous generation starts.

**Assessment:** CAS is the primary defense against duplicate execution across all options. The framework choice does not change this. The JincSAE use case layer must be designed for idempotency at the application level, treating duplicate job delivery as a normal condition. (INFERENCE — consequence of ADR-002 design)

---

### Scenario S3 — DB Commits, Job Dispatch Fails (Lost Dispatch — Primary Differentiator)

This is the most architecturally significant scenario.

**Option A — Procrastinate:** Job enqueue is a PostgreSQL INSERT within the same transaction as the domain state change. If the transaction commits, the job exists. If the transaction rolls back, the job does not exist. There is no dual-write problem. S3 is **structurally impossible**. (FACT — Procrastinate transactional enqueue capability; this is the library's primary design advantage)

**Options B, C, D — External Broker:** After the DB transaction commits, the application must write to an external service (Redis, RabbitMQ, Temporal). If this write fails, S3 occurs. The entity is in a valid state but no job is progressing.

**Mitigation for B, C, D:** A periodic recovery scan queries PostgreSQL for entities in intermediate states with no corresponding in-progress job, and re-enqueues them. Maximum stall time = polling interval.

```python
# Recovery scan pattern (pseudo-code):
async def recovery_scan():
    stuck = await repo.find_content_versions_in(
        status=["VALIDATED", "GENERATED"],
        no_pending_job=True,
        older_than=timedelta(minutes=5)
    )
    for cv in stuck:
        await dispatch_job(cv)
```

This pattern works but has two costs: (1) implementation burden; (2) a stall window of up to the polling interval before detection.

**Option E:** In-process dispatch follows the DB commit in the same asyncio task. However, if the process crashes between commit and dispatch, S3 occurs — and the recovery mechanism is identical to Options B/C/D (a startup scan). The window is larger because there is no background polling loop unless explicitly built.

**Assessment:** Option A is the only candidate that eliminates S3 by architecture. All other options require a compensating recovery scan, which adds implementation complexity and introduces a stall window. (FACT for A; INFERENCE for required mitigation pattern in B/C/D)

---

### Scenario S4 — Job Dispatched, DB Transaction Rolls Back

All options can dispatch a job before the DB transaction commits (incorrect pattern) or after (correct pattern). Assuming correct pattern (dispatch after commit):

If the DB transaction rolls back after job dispatch (e.g., due to application logic detecting an error post-dispatch — an unusual but possible pattern), a worker receives a job referencing state that does not exist or is inconsistent.

**Defense:** The CAS guard in the use case will find `rows_affected = 0` and exit gracefully. The job is consumed without effect. The entity is in whatever state it was in before the failed transaction.

**Assessment:** This scenario resolves gracefully in all options, assuming the CAS-first application design. The framework choice does not materially affect this. (INFERENCE — consequence of ADR-002 CAS design)

---

### Scenario S5 — LLM Provider Timeout

**Pattern:** Worker sends LLM generation request. Provider processes it. Network fails before response arrives. Worker times out.

**Key question:** Is this a technical retry or an editorial regeneration?

Per ADR-002 Invariant 4 and SDD §15:

- **Technical retry:** A short-duration infra failure. The LLM call is retried. The existing ContentVersion in `GENERATED` (or `VALIDATING`) state can be retried without creating a new version — because no new version was ever committed. The retry is at the infrastructure level, not the domain level.
- **Editorial regeneration:** A deliberate business event where content is re-created by editorial decision. Creates a new ContentVersion.

The distinction hinges on whether the generation result was ever persisted. If the LLM returned content and validation committed it (ContentVersion status = `GENERATED` or `VALIDATED`), retry is no longer appropriate — it would require editorial regeneration. If the LLM call itself timed out before any content was committed, a technical retry of the LLM call is correct.

**Framework implications:** All options except E support per-task retry configuration. The retry count and backoff for LLM calls should be configurable independently from publication retries. (FACT for A, B, C, D; INFERENCE for E requiring custom implementation)

**Assessment:** The framework choice must support per-task or per-queue configurable retry policies. All proper queue frameworks support this. The application must implement the distinction between technical retry (LLM call retry) and editorial retry (new ContentVersion) at the use case layer.

---

### Scenario S6 — Publication Timeout (External Side Effect)

This scenario is fully specified in ADR-002 §Publication Recovery Protocol. The async framework must:

1. Support the `PUBLISHING` state transition (domain concern, not framework concern).
2. Allow a periodic recovery worker to scan for `PUBLISHING` records beyond TTL.
3. Create new `PublicationAttempt` records for recovery attempts.

**Framework implications:**

- Option A: The recovery scan job is a Procrastinate periodic task; it queries the PostgreSQL job table and application tables in the same database. Native support. (FACT)
- Options B, C: Recovery scan is an ARQ/Celery periodic task; it queries PostgreSQL via SQLAlchemy. Requires cross-service coordination (Redis queue + PG query in the same job). (FACT — standard pattern)
- Option D: A Temporal workflow can encode the recovery protocol natively. However, this creates the dual-authority concern noted in §5. (INFERENCE)
- Option E: Recovery scan is an asyncio polling loop. Viable but no built-in TTL management. (INFERENCE)

The residual risk of duplicate publication is formally accepted by ADR-002 Decision 2. The framework choice does not eliminate it.

---

### Scenario S7 — Scheduler Crash with Pending Publications

| Option | Schedule Storage | Recovery Mechanism |
| :--- | :--- | :--- |
| A — Procrastinate | PostgreSQL `scheduled_at` column in job table | Worker restart; jobs with `scheduled_at <= now()` are re-claimed automatically |
| B — ARQ | Redis sorted set (score = scheduled timestamp) | Redis durability determines recovery; `appendfsync always` required for full durability |
| B — TaskIQ | Broker-dependent | Varies |
| C — Celery | Celery Beat uses a file-based or DB schedule | Celery Beat restart; schedule re-read from its persistence store |
| D — Temporal | Temporal server state | Temporal server restart; schedule preserved in Temporal state |
| E — App-native | PostgreSQL (polled) | Startup scan re-discovers `SCHEDULED` ContentVersions |

**Assessment:** Option A has the strongest scheduler crash story for the JincSAE MVP: scheduled jobs are PostgreSQL rows with a `scheduled_at` timestamp. If the worker process crashes, the jobs survive in PostgreSQL and are reclaimed on restart without any additional service. Option B's ARQ depends on Redis durability configuration — with default `everysec` sync, up to 1 second of schedules could be lost (FACT — Redis persistence docs). Options B/C/D require broker durability configuration to match Option A's durability guarantees. Option E correctly stores schedule state in PostgreSQL but requires explicit coding to rediscover on startup. (FACT for A; FACT for Redis persistence risk; INFERENCE for E startup behavior)

---

### Scenario S8 — Retry Storm

| Option | Rate Limiting | Exponential Backoff | Jitter | Dead Letter |
| :--- | :--- | :--- | :--- | :--- |
| A — Procrastinate | ✅ Per-queue concurrency limit | ✅ RetryStrategy | ✅ Yes | ✅ Failed jobs in PG table |
| B — ARQ | ⚠️ Worker concurrency limit only | ❌ Manual | ❌ Manual | ⚠️ Manual tracking |
| B — TaskIQ | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| C — Celery | ✅ Rate limits per queue | ✅ Yes | ✅ Yes | ✅ Dead letter queue |
| D — Temporal | ✅ Rate limits in activity options | ✅ Yes | ✅ Yes | ✅ Workflow failure state |
| E — App-native | ❌ Custom | ❌ Custom | ❌ Custom | ❌ Custom |

**Assessment:** ARQ's retry storm resistance is the weakest among proper queue frameworks. Option E has none by default. Celery and Temporal have the most sophisticated rate limiting. Procrastinate's per-queue concurrency limits provide adequate protection for MVP workloads. TaskIQ is competitive. (FACT for Celery, Temporal; FACT for Procrastinate concurrency limits; FACT for ARQ limitations; INFERENCE for MVP adequacy of Procrastinate)

---

## 8. Transaction / Queue Consistency Analysis

### The Dual-Write Failure Point

```
[T1] BEGIN TRANSACTION
[T2]   UPDATE content_versions SET status = 'VALIDATED' WHERE id = $1 AND status = 'GENERATED'
[T3]   INSERT INTO content_version_transitions (...) VALUES (...)
[T4] COMMIT  ← DB state committed
[T5] await queue.enqueue(GeneratePlatformContentJob, content_version_id=$1)
     ↑ If this fails (crash, network, broker down):
     S3 OCCURS: DB is VALIDATED, no job progressing
```

### Pattern Analysis

| Pattern | Mechanism | S3 Eliminates? | Additional Cost |
| :--- | :--- | :---: | :--- |
| P1 — Transactional Outbox | Job INSERT in same PG transaction; relay to external broker | ✅ Yes | Relay process required |
| P2 — Polling Publisher | Periodic scan for stuck entities; re-enqueue | ❌ No (detects; doesn't prevent) | Stall window; duplicate risk |
| P3 — PG-Native Job Table (Procrastinate) | Job IS a PG row; same transaction as state change | ✅ Yes (structural) | Same DB; no relay needed |
| P4 — Direct Dispatch + Recovery Scan | Standard pattern for Redis/Celery/Temporal | ❌ No | Recovery scan; stall window |

**For Option A (Procrastinate):** Pattern P3 applies natively. The job table IS in PostgreSQL. The code is:

```python
# Correct Procrastinate + SQLAlchemy pattern:
async with session.begin():
    # CAS state transition + audit INSERT (ADR-002 Invariant 1)
    await content_version_repo.transition(cv_id, 'GENERATED', 'VALIDATED', actor='SYSTEM')
    # Job enqueue as PostgreSQL INSERT in the SAME transaction
    await generate_task.defer_async(content_version_id=str(cv_id))
# ↑ All committed atomically. S3 is structurally impossible.
```

(FACT — Procrastinate's async defer within SQLAlchemy session is a documented integration pattern)

**For Options B, C, D:** Pattern P4 (post-commit dispatch) is the only viable pattern without introducing a separate outbox relay. The application must additionally implement a recovery scan. The stall window is a function of the polling interval:

```python
# Standard post-commit dispatch (Options B, C, D):
async with session.begin():
    await content_version_repo.transition(cv_id, 'GENERATED', 'VALIDATED', actor='SYSTEM')
# ↑ Committed
await redis_queue.enqueue(GeneratePlatformContentJob, content_version_id=str(cv_id))
# ↑ If this crashes → S3
```

**Conclusion:** Option A eliminates the dual-write problem structurally. Options B, C, D require a recovery scan as a compensating pattern. This is a material architectural difference. (FACT for A mechanism; INFERENCE for S3 risk in B/C/D without recovery scan)

---

## 9. Retry / Recovery Analysis

### Retry Taxonomy for JincSAE

Per SDD §15 and ADR-002, four distinct retry types must be supported:

| Type | Trigger | Framework-Level? | Creates New Entity? |
| :--- | :--- | :---: | :---: |
| Technical Retry (LLM infra) | Transient provider error before commit | ✅ Yes | ❌ No — retries the same call |
| Technical Retry (Social API infra) | Transient platform error (503, 429) | ✅ Yes | ❌ No — retries same PublicationAttempt context |
| Publication Recovery | PUBLISHING TTL exceeded | ✅ Partial (scheduled scan) | ✅ Yes — new PublicationAttempt |
| Editorial Regeneration | Human decision to regenerate | ❌ No (business event, not infra retry) | ✅ Yes — new ContentVersion |

The async framework must support the first two natively. The third must be implemented as a periodic job. The fourth is a domain use case triggered by a human action, not a queue retry.

### Retry Configuration Requirements

The framework must support different retry policies per job type:

- LLM generation jobs: higher retry count, longer backoff (provider rate limits)
- Publication jobs: lower retry count, moderate backoff (critical — must not over-retry)
- Validation jobs: minimal retry (near-deterministic)

All options except E and ARQ support per-task retry configuration.

---

## 10. Scheduling Analysis

The JincSAE requires the following scheduling capabilities:

| Requirement | Description | MVP Precision Need |
| :--- | :--- | :--- |
| Delayed publication | Publish a ContentVersion at a specific future datetime | ≤ 1 minute |
| Periodic recovery scan | Detect stuck PUBLISHING entities | Every 5–15 minutes |
| Periodic dead-letter review | Surface permanently failed jobs | Every hour |

All proper queue frameworks (A, B, C, D) support these natively. Option E requires custom asyncio loop implementation.

**Scheduling storage durability:**

- Option A: `scheduled_at` stored in PostgreSQL job table — durable by ADR-002 accepted infrastructure. (FACT)
- Option B (ARQ): scheduled jobs stored in Redis sorted set — requires Redis persistence for durability. Default Redis configuration (`everysec` sync) may lose up to 1 second of schedules on crash. (FACT)
- Options C, D: similar external durability concerns.

**Conclusion:** Option A provides the most durable scheduling without additional configuration, because scheduled jobs are PostgreSQL rows and PostgreSQL is already configured as the durable state store. (INFERENCE — consequence of ADR-002 persistence decision)

---

## 11. Concurrency Analysis

### LLM Call Parallelism

The pipeline requires generating platform content for 4 platforms per article. These can be parallelized:

```python
# Parallel platform generation (pseudo-code):
await asyncio.gather(
    generate_task.defer(platform="linkedin", brief_id=brief_id),
    generate_task.defer(platform="facebook", brief_id=brief_id),
    generate_task.defer(platform="instagram", brief_id=brief_id),
    generate_task.defer(platform="bluesky", brief_id=brief_id),
)
```

All asyncio-native options (A, B-ARQ, B-TaskIQ, D, E) support this pattern. Celery requires gevent or asyncio integration. (FACT)

### Worker Concurrency

| Option | Worker Concurrency Model |
| :--- | :--- |
| A — Procrastinate | Per-queue concurrency limit; single async worker can run multiple concurrent jobs |
| B — ARQ | Single async worker; configurable `max_jobs` per worker instance |
| B — TaskIQ | Worker concurrency configurable per broker |
| C — Celery | Process-based (prefork) or gevent concurrency; not asyncio-native |
| D — Temporal | Activity worker thread pool or asyncio workers; highly configurable |
| E — App-native | asyncio `gather` for parallel execution within process |

### CAS as Concurrency Guard

Regardless of worker concurrency model, the CAS guard in PostgreSQL prevents duplicate state transitions. Multiple workers claiming the same job will all attempt the same CAS update; only one will succeed. (FACT — ADR-002 §Concurrency Model)

The concurrency analysis conclusion is that proper queue concurrency parameters are secondary to CAS correctness. The framework must support concurrent job execution; CAS handles the domain-level mutual exclusion.

---

## 12. Operational Analysis

| Dimension | A (Procrastinate) | B (ARQ) | B (TaskIQ) | C (Celery) | D (Temporal) | E (App-native) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Additional infra services | 0 | 1 (Redis) | 1 (Redis) | 2–4 | 2–3 | 0 |
| Local dev services (docker-compose) | 0 extra | 1 extra | 1 extra | 2–4 extra | 2–3 extra | 0 extra |
| Deployment units (processes) | 1 worker | 1 worker + Redis | 1 worker + Redis | 3+ (worker + Beat + broker + opt. Flower) | 2–3 + Temporal server | Inline with API |
| Schema additions to PG | 4 tables | 0 | 0 | 0 (or 1 if PG result backend) | 0 (own DB) | 0 |
| Monitoring without extra tools | SQL query | Redis CLI | Broker CLI | Flower (extra service) | Temporal Web UI (extra service) | Python logs only |
| Failure surface | PG | PG + Redis | PG + Redis | PG + broker + Beat + result backend | PG + Temporal server + Temporal DB | PG + process |

(FACT for all service counts based on documented deployment requirements)

**MVP Operational Complexity Ranking:**

1. Option A — Procrastinate (lowest: 0 new services)
2. Option E — App-native (0 new services, but implementation burden)
3. Options B — ARQ/TaskIQ (1 new service: Redis)
4. Option C — Celery (2–4 new services)
5. Option D — Temporal (2–3 new services + completely different programming model)

### PostgreSQL Contention Concern (Option A)

Having job tables in the same PostgreSQL instance as domain tables creates a potential contention point under high job volume. For the JincSAE MVP workload (low double-digit articles per day), this is not a concern. (INFERENCE — contention only relevant at hundreds of jobs/second; MVP is far below this)

If job volume grows materially, the job tables can be migrated to a separate PostgreSQL instance or schema without changing the application interface. (INFERENCE — standard operational evolution path)

---

## 13. Reversibility Analysis

### What Couples to the Queue Choice?

The async framework is used in the **infrastructure layer only** (ADR-002 Invariant 7). The domain layer has no queue imports. Use cases do not reference queue primitives.

The coupling points are:

1. **Task definitions** — functions decorated with `@task` or equivalent. Infrastructure layer only.
2. **Job dispatch calls** — `task.defer(...)`. Application layer → infrastructure layer boundary.
3. **Worker process configuration** — startup, broker URL, worker settings.
4. **Periodic task definitions** — scheduled job registrations.
5. **Recovery scan implementations** — periodic jobs that poll PostgreSQL.

**Migration cost estimation:**

| Migration Type | Effort |
| :--- | :--- |
| A → B (Procrastinate → ARQ/TaskIQ) | Medium: change task decorators + dispatch calls + add Redis; recover scan moves to Redis-backed scheduler |
| B → A (ARQ → Procrastinate) | Medium: change decorators + remove Redis + dispatch within transactions |
| A/B → C (→ Celery) | Medium: Celery task decorators + broker setup + Beat configuration |
| Any → D (→ Temporal) | High: complete workflow redesign; Temporal's programming model is fundamentally different |
| Any → E (→ App-native) | Low: remove queue; implement custom loop; significant regression in features |
| E → Any | Low: add queue; replace polling loop |

**Conclusion:** Switching between A, B, and C is a medium-effort infrastructure layer change. Switching to or from D is high-effort due to the Temporal programming model. Option A is not materially harder to replace than Option B; both are infrastructure concerns. Option E is the most reversible starting point but the least capable. (INFERENCE)

---

## 14. Decision Matrix

### Scoring

Scale: 1 (poor) to 5 (excellent).
Weights: Critical (3×), High (2×), Medium (1×).

| Driver | Weight | A (Procrastinate) | B-ARQ | B-TaskIQ | C (Celery) | D (Temporal) | E (App-native) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1. Operational Simplicity | 3× | **5** | 4 | 4 | 2 | 2 | **5** |
| 2. Python/asyncio Compat. | 3× | **5** | **5** | **5** | 2 | 4 | **5** |
| 3. PG Transaction Integration | 3× | **5** | 2 | 2 | 2 | 2 | 3 |
| 4. Crash Recovery | 2× | **5** | 4 | 4 | 4 | **5** | 2 |
| 5. Retry Semantics | 2× | **5** | 3 | 4 | **5** | **5** | 1 |
| 6. Delayed/Scheduled Exec. | 2× | **5** | 4 | 4 | 4 | **5** | 3 |
| 7. Idempotent Exec. Support | 2× | 4 | 3 | 4 | 4 | **5** | 2 |
| 8. Observability | 2× | 4 | 3 | 4 | 4 | **5** | 2 |
| 9. Domain Independence | 2× | **5** | **5** | **5** | **5** | **5** | **5** |
| 10. Dev / Testing Complexity | 1× | 4 | 4 | 3 | 3 | 2 | **5** |
| 11. Scalability | 1× | 4 | 4 | 4 | **5** | **5** | 2 |
| 12. Reversibility | 1× | 4 | 4 | 4 | 3 | 2 | **5** |
| 13. Vendor Lock-in | 1× | **5** | 3 | 3 | 3 | 2 | **5** |

### Weighted Scores

Critical drivers (×3): Drivers 1, 2, 3
High drivers (×2): Drivers 4–9
Medium drivers (×1): Drivers 10–13

| Option | Critical (3×) | High (2×) | Medium (1×) | **Total** |
| :--- | :---: | :---: | :---: | :---: |
| A — Procrastinate | (5+5+5)×3 = **45** | (5+5+5+4+4+5)×2 = **56** | (4+4+4+5)×1 = **17** | **118** |
| B — ARQ | (4+5+2)×3 = **33** | (4+3+4+3+3+5)×2 = **44** | (4+4+4+3)×1 = **15** | **92** |
| B — TaskIQ | (4+5+2)×3 = **33** | (4+4+4+4+4+5)×2 = **50** | (3+4+4+3)×1 = **14** | **97** |
| C — Celery | (2+2+2)×3 = **18** | (4+5+4+4+4+5)×2 = **52** | (3+5+3+3)×1 = **14** | **84** |
| D — Temporal | (2+4+2)×3 = **24** | (5+5+5+5+5+5)×2 = **60** | (2+5+2+2)×1 = **11** | **95** |
| E — App-native | (5+5+3)×3 = **39** | (2+1+3+2+2+5)×2 = **30** | (5+2+5+5)×1 = **17** | **86** |

**Option A (Procrastinate) scores highest** (118), driven by its perfect scores on the three Critical drivers. Its lead is primarily due to Driver 3 (PostgreSQL Transaction Integration, scored 5 vs. 2 for all Redis/external broker options). This is the most consequential driver for the JincSAE architecture given ADR-002's invariants.

**Scoring notes:**

- Option A's score of 4 on Idempotency (Driver 7) reflects that idempotency is primarily an application concern (CAS guards), not a framework feature; all options are roughly equivalent here, with Temporal scoring higher due to built-in workflow idempotency key support. (INFERENCE)
- Option D (Temporal) scores highest on Crash Recovery, Retry, Scheduling, Idempotency, and Observability — but its Critical driver scores are 24 (vs. A's 45), reflecting the dual-authority concern and additional infrastructure burden. (INFERENCE from architecture analysis)
- Option E scores well on Simplicity and Reversibility but fails on Retry, Scheduling, Recovery, and Observability — making it unsuitable as a production queue strategy. (FACT — no built-in capabilities)

---

## 15. Counterfactuals

### What If Option A Is Rejected?

**If Procrastinate is rejected** (e.g., PG schema contention concern, community size concern, or operator preference for Redis):

- **Best alternative:** TaskIQ (B-TaskIQ, score 97) — asyncio-native, pluggable brokers, built-in retry with backoff. Requires Redis (+1 infra service) and a compensating recovery scan for S3.
- **The recovery scan becomes mandatory** for S3 mitigation. Its maximum stall time must be explicitly defined and accepted.

### What If PG Contention Becomes a Problem at Scale?

If article volume grows significantly (hundreds per day, multiple LLM calls in parallel), the PostgreSQL job table may become a contention point.

- **Migration path:** Switch to TaskIQ or ARQ at the infrastructure layer. Domain layer unchanged. Use cases unchanged. ADR-002 invariants unchanged. Estimated migration effort: medium (infrastructure layer only, per Reversibility Analysis §13).
- This validates Option A as a good starting choice with a clear evolution path.

### What If a Redis Cache Is Already Required for Other Reasons?

If a future ADR (e.g., API rate limiting, session cache) introduces Redis, the marginal cost of Option B drops from "adding a new service" to "extending an existing service." This could upgrade Option B's Operational Simplicity score. However, as of this analysis, no such Redis requirement is evident from the PRD or accepted ADRs. (UNKNOWN — depends on future ADRs)

---

## 16. Risks

| Risk | Severity | Option Affected | Mitigation |
| :--- | :--- | :--- | :--- |
| Procrastinate community size | Low | A | Active maintenance confirmed; production usage documented; PostgreSQL is proven infrastructure |
| PG job table contention at scale | Medium | A | Per-queue concurrency limits; schema separation; migration to Redis-backed option if needed |
| S3 (Lost Dispatch) under Options B/C/D | High | B, C, D | Mandatory recovery scan implementation; defined maximum stall time |
| Redis data loss on broker crash (ARQ) | Medium | B-ARQ | Redis `appendfsync always` configuration; or use Option A |
| Celery asyncio incomplete support | High | C | Eliminates C from MVP consideration without gevent workarounds |
| Temporal dual-authority state conflict | Medium | D | Careful architectural discipline; Temporal as orchestrator, PG as state store (complex) |
| App-native (E) production inadequacy | High | E | E is a prototype approach; must be replaced before any meaningful publication volume |

---

## 17. Unknowns

| Unknown | Impact | Required Before Decision |
| :--- | :--- | :--- |
| Article publication volume target (PRD gap) | Determines if PG-native queue is sufficient long-term | Not blocking for MVP decision |
| Operations team capacity for Redis management | Affects B-series operational complexity score | Not blocking — scored conservatively |
| Deployment environment (cloud provider) | Managed Redis may reduce Option B operational burden | Deferred to Infrastructure ADR |
| Future Redis requirement from other ADRs (caching, sessions) | May reduce marginal cost of Option B | Not blocking — scored on current requirements |
| Procrastinate production adoption breadth | Confidence in long-term maintenance | INFERENCE — confirmed active maintenance |

---

## 18. Preliminary Recommendation

### Recommended Option: A — Procrastinate (PostgreSQL-Native Queue)

**Primary reason:** Option A is the only candidate that structurally eliminates Scenario S3 (Lost Dispatch) by making job enqueue part of the PostgreSQL transaction. This is the single most important architectural concern for the JincSAE system, given ADR-002's invariant that PostgreSQL is the authoritative state store and the explicit requirement that no domain state must be lost silently.

**Secondary reasons:**

- Zero additional infrastructure services. The MVP deploys with one database (PostgreSQL) and one worker process. The operational surface is minimal.
- Native asyncio support. `async def` job functions share the same SQLAlchemy async session context, enabling the mandatory CAS + audit INSERT transaction boundary.
- Built-in support for all required capabilities: delayed jobs, periodic tasks, retry with exponential backoff and jitter, per-queue concurrency limits, and failure observability via PostgreSQL queries.
- Consistency with the accepted ADR-002 principle: the queue is part of PostgreSQL, not a separate truth-bearing system.

**Rejected options and primary reasons:**

| Option | Primary Rejection Reason |
| :--- | :--- |
| B — ARQ | S3 risk; manual retry backoff; no native jitter; Redis durability concern for schedule storage |
| B — TaskIQ | S3 risk; +1 infrastructure service (Redis); weaker integration with PG transactions |
| C — Celery | Incomplete asyncio support; 2–4 additional infrastructure services; async workarounds required |
| D — Temporal | Dual-authority concern with ADR-002's PostgreSQL authority principle; MVP complexity disproportionate to workload |
| E — App-native | No built-in retry semantics; no dead-letter; no formal scheduling; unsuitable for production |
| B — RQ | Eliminated at evaluation entry — synchronous workers incompatible with asyncio architecture |

**Conditions that would change the recommendation:**

1. If article volume grows to hundreds per day and PG job table contention becomes measurable → migrate to TaskIQ (B-TaskIQ) with a recovery scan.
2. If Redis is introduced for another reason (caching, sessions) → re-evaluate Option B with reduced marginal operational cost.
3. If the system evolves to multi-step sagas with complex branching across many external services → evaluate Temporal for those specific workflow modules.
4. If Procrastinate maintenance is abandoned → migrate to TaskIQ (compatible interface concepts, same infrastructure if Option A → A+Redis path is taken).

---

## 19. Evidence Gaps

| Gap | Type | Impact on Recommendation |
| :--- | :--- | :--- |
| Procrastinate performance benchmarks at JincSAE scale | UNKNOWN | Low — MVP volume is far below any known contention threshold |
| Procrastinate + SQLAlchemy async session sharing in production | INFERENCE from docs | Medium — should be verified in integration test before acceptance |
| ARQ retry storm behavior in production | UNKNOWN | Medium if ARQ chosen; not relevant if A accepted |
| Redis `appendfsync` configuration cost on managed Redis services | UNKNOWN | Only relevant if B chosen |
| Temporal Python SDK production stability score | INFERENCE (SDK marked stable but Temporal is complex) | Only relevant if D chosen |

**The recommendation does not depend on any of the identified evidence gaps.** The structural advantage of Option A (transactional enqueue) is verifiable from library documentation and does not require production benchmarks to establish. (FACT — Procrastinate transactional integration is documented and testable)

---

## 20. Red Team Attack Surface

The following claims in this analysis are the most vulnerable to adversarial challenge. The Architecture Review and Red Team should focus their attacks here:

| Claim | Vulnerability | Potential Falsification |
| :--- | :--- | :--- |
| "Procrastinate transactional enqueue structurally eliminates S3" | True but requires correct usage — if the developer calls `defer` outside the transaction context, S3 is not eliminated | Demonstrate a code path where S3 occurs despite Procrastinate being chosen |
| "PG job table contention is not a concern at MVP scale" | Based on volume inference; no PRD volume target exists | If PRD is updated with high-volume requirement, contention must be re-evaluated |
| "Celery asyncio is incomplete/experimental" | This claim is based on Celery 5.x documentation as of analysis date; Celery may have improved | Provide evidence of full asyncio native support in current Celery release |
| "Option E is inadequate for production" | True for any meaningful scale, but for a prototype or early MVP this may be premature to dismiss | Define the threshold at which E becomes unacceptable; it may be valid for the very first deployment |
| "Domain independence (Driver 9) is equally achievable by all options" | True if the hexagonal architecture is respected; requires implementation discipline | Show a design where queue primitives leak into the domain layer despite framework choice |
| "Temporal has a dual-authority concern with ADR-002" | This is an architectural inference, not a direct Temporal limitation | Design a Temporal + PostgreSQL integration where Temporal orchestrates without owning domain state; evaluate if this resolves the concern |

---

*This document is an ANALYSIS artifact. Status: `PROPOSED FOR ARCHITECTURE REVIEW`. It must not be treated as an accepted decision. The next step in the formal process is Architecture Review → (optional Red Team) → Reconciliation → Human Decision → ADR-003-AsyncStrategy.md (ACCEPTED).*
