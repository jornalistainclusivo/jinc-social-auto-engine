---
briefing-id: MASTER_BRIEFING_ADR-003
title: "Async Processing, Background Jobs & Workflow Execution — ADR-003 Creator Briefing"
status: READY FOR ADR-003 ANALYSIS
authority-chain:
  - docs/ENGINEERING_CONSTITUTION.md
  - docs/PRD.md
  - docs/SDD.md
  - docs/adr/ADR-001-Runtime-Language.md
  - docs/adr/ADR-002-Persistence-Strategy.md
created-at: 2026-08-31
---

# MASTER BRIEFING — ADR-003 Creator

# Async Processing, Background Jobs & Workflow Execution

---

## 0. Purpose and Scope of This Document

This is a planning briefing. It does NOT make any technology decision.

It instructs the ADR-003 Creator agent on how to produce the authoritative
**`docs/adr/ADR-003-Analysis.md`** artifact — including its scope, constraints,
evaluation methodology, failure scenarios, and required sections.

The ADR-003 Creator must read this document in full before writing a single word
of analysis.

---

## 1. Authoritative Artifacts to Read Before Analysis

The ADR-003 Creator must read all of the following documents completely before
starting the analysis. Failure to do so may produce an analysis inconsistent
with accepted decisions.

| Priority | Artifact | Why It Matters for ADR-003 |
| :---: | :--- | :--- |
| 1 | `docs/ENGINEERING_CONSTITUTION.md` | Idempotency, explicit states, no silent failure, domain independence — all constrain the async architecture |
| 2 | `docs/PRD.md` | Defines the actual workload: article volume, platforms, team size, MVP scope |
| 3 | `docs/SDD.md` | Defines the logical architecture modules that async processing must serve |
| 4 | `docs/adr/ADR-001-Runtime-Language.md` | Python is the runtime. All async options must be Python-compatible. |
| 5 | `docs/adr/ADR-002-Persistence-Strategy.md` | PostgreSQL is the state store. The async layer must respect all 7 locked invariants. |

**Do not contradict accepted ADRs. Do not reopen closed decisions.**

---

## 2. Accepted Architectural Baseline (Non-Negotiable Constraints)

The following decisions are ACCEPTED and immutable. ADR-003 must treat them as
architectural constraints, not as options.

### From ADR-001 — Python Runtime

All async and background execution solutions must be Python-compatible.
Node.js-native tools (e.g., BullMQ) are not in scope.

### From ADR-002 — PostgreSQL + Hybrid Audit

The following 7 invariants are locked and binding on the async architecture:

| # | Invariant | Impact on ADR-003 |
| :--- | :--- | :--- |
| 1 | CAS UPDATE + audit INSERT in one explicit DB transaction | Background workers must execute this atomic pair; job dispatch must not split it |
| 2 | Audit history is append-only | Workers must INSERT new audit rows, never UPDATE existing ones |
| 3 | Audited entities use soft-delete | Workers must not hard-delete any entity with an audit chain |
| 4 | Regeneration creates a new ContentVersion | A "retry generation" job must create a new entity, not overwrite |
| 5 | PublicationAttempt is immutable | Each retry attempt must create a new PublicationAttempt row |
| 6 | Retry = new PublicationAttempt record | Workers may not modify status of an existing PublicationAttempt |
| 7 | Domain layer must not import queue infrastructure | The async queue library must live in the infrastructure layer |

### Core Architectural Principle

> **The async/job system executes work. PostgreSQL remains the authoritative source of domain state.**

Workers may fail, restart, or duplicate execution. Correctness depends on:

- persisted state;
- transaction boundaries (ADR-002 Invariant 1);
- CAS concurrency guards (ADR-002 Invariant 6 / §Concurrency Model);
- idempotent use cases;
- explicit retry policies.

**The queue must never become the source of truth.** If the queue is lost or
the broker crashes, domain state must remain consistent in PostgreSQL.

---

## 3. Problem to Be Decided

The JincSAE requires an execution mechanism for the following categories of asynchronous work:

### 3.1 Pipeline Jobs (Long-running, LLM-dependent)

| Job | Trigger | Latency Tolerance |
| :--- | :--- | :--- |
| Article analysis (LLM) | Webhook received | Seconds–minutes |
| Editorial brief generation (LLM) | Analysis complete | Seconds–minutes |
| Platform content generation (LLM, per platform) | Brief ready | Seconds–minutes |
| Content validation | Generation complete | Seconds |

### 3.2 Publication Jobs (External API, reliability-critical)

| Job | Trigger | Latency Tolerance |
| :--- | :--- | :--- |
| Scheduled publication dispatch | Approval + schedule time | Punctual (within ~1min) |
| Publication retry | PUBLISH_FAILED or PUBLISHING stuck | Controlled backoff |
| Publication recovery scan | PUBLISHING beyond TTL | Periodic |

### 3.3 Maintenance Jobs (Periodic, low-criticality)

| Job | Trigger | Latency Tolerance |
| :--- | :--- | :--- |
| PUBLISHING state TTL check | Periodic | Minutes |
| Dead-letter / stuck-job detection | Periodic | Minutes |

### 3.4 Key Behavioral Requirements

- **Delayed execution:** Publication must be schedulable for a future time.
- **Retry with backoff:** LLM and social API calls require exponential backoff with jitter.
- **Crash recovery:** A worker crash must not lose enqueued work permanently.
- **Duplicate delivery:** A job may be delivered more than once; use cases must handle this.
- **No domain coupling:** Workers dispatch use cases; they do not own domain state.

---

## 4. Candidate Options to Evaluate

The analysis must evaluate all of the following options. **No technology may be
selected or eliminated without going through the comparative evaluation.**

### Option A — PostgreSQL-Native Job Queue

Use PostgreSQL itself as the job broker via a Python-compatible library.

**Primary candidate:** [Procrastinate](https://procrastinate.readthedocs.io/)  
(Python-native, asyncio-compatible, PostgreSQL-backed, no separate broker)

**Key questions to evaluate:**

- Does it support delayed jobs, periodic tasks, and retry with backoff?
- Does it allow jobs to be enqueued atomically within a PostgreSQL transaction?
  (This is the critical Transactional Outbox question — see §9.)
- What is the crash recovery mechanism?
- How does it handle duplicate delivery?
- What are the operational bounds (jobs/sec) for the MVP workload?
- Does it add significant schema complexity alongside the domain schema?

**Expected advantage:** Zero additional infrastructure. If jobs are enqueued in
the same transaction as domain state changes, the DB → Queue dual-write problem
(Scenario S3) is eliminated by architecture.

**Evidence type required:** FACT for any claimed capability; INFERENCE for
performance bounds; ASSUMPTION where data is unavailable.

---

### Option B — Redis-Backed Python Task Queue (Modern Alternatives)

Use a Redis-backed async task queue. **Do not default to Celery** — evaluate
the contemporary Python ecosystem.

**Primary candidates to evaluate:**

- [TaskIQ](https://taskiq-python.github.io/) — asyncio-native, pluggable brokers
- [RQ (Redis Queue)](https://python-rq.org/) — simpler, Redis-only, widely used
- [ARQ](https://arq-docs.helpmanual.io/) — asyncio-native, Redis-backed, minimal

**Key questions to evaluate:**

- Does it support asyncio natively (required: ADR-001 Python async pattern)?
- Does it support delayed jobs and scheduled execution?
- What is the retry semantics model (at-least-once, at-most-once)?
- Can jobs be enqueued transactionally with the DB commit? If not, how is
  Scenario S3 (DB commits but job never enqueued) handled?
- What is the operational cost of a Redis instance for the MVP?
- What is the crash recovery guarantee when Redis is the broker?

**Evidence type required:** Clearly distinguish between library documentation
claims (FACT), inferences from architecture (INFERENCE), and gaps (OPEN).

---

### Option C — Celery (Mature Ecosystem Option)

Evaluate Celery as the established Python background job framework.

**Key questions to evaluate:**

- What broker does Celery require? What result backend?
- Is Celery asyncio-compatible? (Celery 5.x + asyncio: verify integration quality)
- What is the retry semantics model?
- Can tasks be enqueued transactionally with a DB commit?
- What is the operational complexity of Celery + broker for the MVP?
- What are Celery's known failure modes with respect to duplicate delivery?
- How does Celery compare to TaskIQ or ARQ for a Python async-first architecture?

**Do not assume Celery is the default.** It is included because it is mature
and widely known. It must earn its recommendation through the decision matrix.

---

### Option D — Durable Workflow Engine (Temporal)

Evaluate Temporal as a high-durability workflow engine.

**Key questions to evaluate:**

- What additional infrastructure does Temporal require?
- How does Temporal's durability model interact with ADR-002's PostgreSQL
  invariants? (Temporal maintains its own state store — is this in conflict?)
- Does Temporal support Python SDK at production quality?
- What is the learning curve and team burden for the MVP?
- What problem does Temporal solve that the simpler options cannot?
- Apply a high burden of proof: Temporal must justify its complexity against the
  PRD's MVP scope.

**Evidence type required:** Do not assume Temporal's capabilities. Verify claims
with explicit source references in the analysis.

---

### Option E — Application-Native Scheduling (Minimal Infrastructure)

Evaluate whether the MVP can be served by:

- PostgreSQL for state persistence (ADR-002, already accepted);
- A simple asyncio background task or thread pool within the FastAPI process;
- Periodic polling of PostgreSQL for pending work.

**Key questions to evaluate:**

- Is an in-process worker sufficient for the MVP workload?
- What are the failure modes if the FastAPI process crashes?
- Can scheduled publication (future datetime) be implemented without a separate
  scheduler process?
- At what point does this approach require replacement?
- Is this an anti-pattern, or a legitimate MVP starting point?

**Evidence type required:** This is a viable option that deserves honest
evaluation, not dismissal. Identify specific failure modes that would prevent
this from working.

---

## 5. Mandatory Decision Drivers (No Double-Counting)

The analysis must evaluate all options against these drivers. Each driver must
appear exactly once. Do not split a single concern into multiple sub-drivers
that effectively double-count the same property.

| # | Driver | Definition |
| :--- | :--- | :--- |
| 1 | **Operational Simplicity** | Number of distinct infrastructure services required to operate the system. Lower = better. |
| 2 | **Python & asyncio Compatibility** | Native asyncio support. First-class Python SDK. Active maintenance. |
| 3 | **PostgreSQL Integration** | Ability to participate in, or correctly interoperate with, PostgreSQL transactions (ADR-002 Invariant 1). |
| 4 | **Crash Recovery** | System behavior when a worker process crashes during job execution. Can work be reclaimed without data loss? |
| 5 | **Retry Semantics** | Support for at-least-once delivery, exponential backoff with jitter, configurable retry limits, and dead-letter destination. |
| 6 | **Delayed & Scheduled Execution** | Native support for jobs enqueued to run at a specific future datetime. |
| 7 | **Idempotent Execution Support** | Does the framework facilitate idempotent job design? How does it handle duplicate delivery? |
| 8 | **Observability** | Job status visibility, failure logs, queue depth, worker health. |
| 9 | **Domain Independence** | Can queue/worker code be isolated to the infrastructure layer? Does the domain model import queue primitives? |
| 10 | **Scalability for Foreseeable Growth** | Suitability from MVP single-worker to small newsroom scale without architectural change. |
| 11 | **Development & Testing Complexity** | Ease of local development setup, unit testability of jobs, integration test support. |
| 12 | **Reversibility / Evolution Path** | Cost of migrating away from this choice if requirements change. |
| 13 | **Vendor/Infrastructure Lock-in** | Dependency on proprietary services or specific cloud providers. |

**Prohibited drivers:**

- "X is popular" — not a technical driver.
- "The team is familiar with X" — the team composition is not specified in PRD.
- "X is the industry standard" — standards change; evaluate on technical merit.

---

## 6. Critical Failure Scenarios (Mandatory Analysis)

Each option must be analyzed against all 8 scenarios. For each scenario, state:

1. What happens under this option?
2. Does the system remain correct according to ADR-002 invariants?
3. What recovery mechanism applies?

### Scenario S1 — Worker Crash After Job Claim, Before Completion

A worker claims a job (transitions the domain entity to an in-progress state)
and then crashes before completing the use case.

**Required analysis:**

- How does the job re-enter the queue?
- How is the in-progress state in PostgreSQL recovered?
- Is human intervention required, or is it automatic?
- Does recovery respect ADR-002 Invariant 1 (atomic CAS + audit)?

---

### Scenario S2 — Duplicate Execution

Two workers receive and execute the same logical job simultaneously.

**Required analysis:**

- What prevents both executions from completing successfully?
- The ADR-002 CAS guard is the primary defense — how does each async option
  interact with it?
- If both CAS operations succeed (they shouldn't), what is the damage?
- Does the option make idempotent design easier or harder?

---

### Scenario S3 — DB Commits, Job Dispatch Fails (The Lost Dispatch Problem)

This is the most architecturally significant failure scenario for this ADR.

The domain state transition commits in PostgreSQL (e.g., ContentVersion status
becomes VALIDATED). The subsequent attempt to enqueue the next job in the
pipeline (e.g., GeneratePlatformContentJob) fails — network error, broker down,
process crash.

Result: The entity is in a valid state but no async work is progressing. The
pipeline is silently stalled.

**Required analysis:**

- Does the option prevent this scenario by architecture (e.g., transactional
  enqueue in the same PostgreSQL transaction)?
- If not, how is it detected and recovered?
- Is a polling-based recovery scan (periodic check for entities stuck in
  intermediate states) sufficient?
- What is the maximum stall time before detection?

**This scenario must receive dedicated analysis in the Transactional Outbox
section (§9 of the analysis). It is a primary differentiator between options.**

---

### Scenario S4 — Job Dispatched, DB Transaction Rolls Back

A job is enqueued, but the database transaction containing the corresponding
state change rolls back (e.g., due to a constraint violation or application
error discovered after the enqueue call).

Result: A worker receives a job referencing state that does not exist or is
inconsistent with what the job expects.

**Required analysis:**

- How does the worker detect that the referenced entity is in an unexpected state?
- The CAS guard will fail — how is this failure surfaced?
- Is "CAS returns 0 rows → exit gracefully" a sufficient application-level
  contract, or does it leave orphaned jobs accumulating in the queue?
- How does each option handle permanent orphans (jobs that can never succeed)?

---

### Scenario S5 — LLM Provider Timeout

The application sends a generation request to an LLM provider. The provider
may have received and processed the request, but the HTTP response is lost.

**Required analysis:**

- What does the worker do when it times out?
- Does it retry the LLM call?
- If the LLM generated a response that was never received, does retrying produce
  a second generation?
- Does ADR-002 Invariant 4 (regeneration = new ContentVersion) apply here, or
  is this a technical retry at the infrastructure level?
- How does each option support configuring separate retry policies for different
  job types?

---

### Scenario S6 — Publication Timeout (External Side Effect)

The worker dispatches a post to an external social platform. The platform may
have published the post successfully, but the worker never receives the HTTP 200
response (network failure, timeout, worker crash).

**Required analysis:**

- How does each async option interact with the ADR-002 PUBLISHING state and
  recovery protocol?
- Does the option support the TTL-based recovery scan described in ADR-002?
- The residual risk of duplicate publication is formally accepted (ADR-002
  Decision 2). How does the chosen option minimize the probability of triggering
  this risk?
- Does the option support per-job metadata (e.g., storing `external_publication_id`
  on the job record) that could assist recovery?

---

### Scenario S7 — Scheduler Crash with Pending Scheduled Publications

The scheduler process crashes while there are ContentVersions in SCHEDULED state
with future publication datetimes.

**Required analysis:**

- How does the scheduler recover?
- Are pending scheduled jobs stored in the broker (risk: broker failure = lost
  schedule) or in PostgreSQL (risk: requires polling)?
- Can the schedule be reconstructed from PostgreSQL state alone?
- Is there a risk that a publication fires twice (once before crash, once after
  recovery)?

---

### Scenario S8 — Retry Storm

A social platform outage causes all active publication jobs to fail and retry.
With exponential backoff disabled or misconfigured, this could produce thousands
of retry attempts per minute.

**Required analysis:**

- Does the option support per-queue or per-job-type rate limiting?
- Does it support exponential backoff with configurable jitter?
- Does it support a maximum retry count with dead-letter routing?
- What is the operational visibility into a retry storm in progress?
- Can it be paused or throttled without code deployment?

---

## 7. Transactional Outbox Analysis (Mandatory Section)

This is one of the most important sections of the ADR-003 analysis.

### The Problem

> How can a committed domain state transition reliably cause asynchronous work
> without creating a DB → Queue dual-write failure (Scenario S3)?

The naive pattern is:

```
1. UPDATE domain state in PostgreSQL (commit)
2. Enqueue job in queue broker (separate call)
```

If step 2 fails for any reason (crash, network, broker down), the pipeline is
stalled without any detection mechanism.

### Patterns to Evaluate

The analysis must evaluate the following patterns and their applicability to the
JincSAE MVP:

#### Pattern P1 — Transactional Outbox

Enqueue jobs by INSERT into a PostgreSQL `outbox` table within the same
transaction as the domain state change. A separate process (relay) reads from
the outbox and publishes to the external broker.

- **Advantage:** Eliminates the dual-write problem entirely by making job
  dispatch part of the PostgreSQL transaction.
- **Advantage for PostgreSQL-native options:** If the job table IS in PostgreSQL
  (e.g., Procrastinate), the outbox IS the job table — no relay process needed.
- **Cost:** Requires an outbox table and a relay process if the broker is
  external.

#### Pattern P2 — Polling Publisher

A background scanner periodically queries PostgreSQL for entities in intermediate
states (e.g., VALIDATED but no pending generation job) and enqueues missing jobs.

- **Advantage:** Simple to implement; no outbox schema changes.
- **Cost:** Maximum stall time equals the polling interval. Detection is
  reactive, not proactive.
- **Risk:** Under high load, the scanner may produce duplicate jobs (Scenario
  S4).

#### Pattern P3 — PostgreSQL-Native Job Table

If the async option stores jobs in PostgreSQL (Option A), enqueuing within the
same transaction is trivially correct. There is no dual-write problem because
DB and queue share the same transaction scope.

- **Advantage:** Structural solution; Scenario S3 is impossible by architecture.
- **Cost:** Queues in the same DB may create contention or schema complexity.

#### Pattern P4 — Direct Dispatch with Recovery Scan (Accepted ADR-002 Residual Pattern)

Dispatch jobs after commit. Accept the dual-write risk. Implement a periodic
recovery scan that detects stalled entities and re-enqueues them.

- **Advantage:** Simpler implementation; no outbox schema.
- **Risk:** Stall detection latency = polling interval. Maximum stall time must
  be defined and accepted by the team.
- **Context:** This is the pattern currently implicit in ADR-002. The analysis
  must evaluate whether it is sufficient or whether P1 or P3 is needed.

### Required Analysis Outcome

The analysis must state explicitly:

1. Which pattern(s) are compatible with each candidate option.
2. Whether the Transactional Outbox (P1) is necessary for the JincSAE MVP, or
   whether P4 (Recovery Scan) with a defined maximum stall time is acceptable.
3. If P4 is chosen, what is the maximum acceptable stall time, and how is it
   monitored?

---

## 8. Python Ecosystem Analysis (Mandatory Section)

This section must evaluate the Python-specific landscape for async job execution
as of the analysis date.

### Required Sub-Analyses

#### 8.1 asyncio Compatibility

The JincSAE is Python-based with async patterns (FastAPI, asyncpg, SQLAlchemy
async). The ADR-003 Creator must verify:

- Does each option support `asyncio` natively (define jobs as `async def`)?
- Or does it require thread-pool wrapping (sync workers in a thread)?
- What are the implications of sync workers in an async codebase?

#### 8.2 Pydantic Integration

ADR-001 establishes Pydantic as the runtime validation layer. Job payloads
should be validated:

- Does the option support typed job payloads?
- Can job input be a Pydantic model?
- How are serialization errors handled?

#### 8.3 FastAPI Integration

The API layer is FastAPI (established by ADR-001 Python ecosystem selection):

- Does the option have documented FastAPI integration patterns?
- Can job dispatch happen from within a FastAPI request handler within an
  `async with session.begin()` block?
- How is the lifecycle (startup/shutdown) managed in FastAPI?

#### 8.4 Testing Support

The Engineering Constitution requires testability:

- Can individual job/task functions be unit-tested without starting the full
  worker infrastructure?
- Is there an in-memory or in-process test mode?
- Can jobs be tested in isolation from the broker?

---

## 9. Operational Complexity Analysis (Mandatory Section)

The analysis must quantify the operational cost of each option:

| Dimension | What to Assess |
| :--- | :--- |
| **Infrastructure services count** | How many additional infrastructure services does this option require (broker, result backend, scheduler, relay)? |
| **Local development setup** | How many `docker-compose` services must a developer run locally? |
| **Deployment units** | How many separate processes must be deployed and monitored in production? |
| **Monitoring / observability** | What built-in dashboards, metrics, or logging does the option provide? |
| **Failure surface** | How many distinct failure points does the option introduce? |
| **Schema impact** | Does the option add tables to the PostgreSQL schema? How many? |
| **Configuration complexity** | Number of configuration parameters required for basic operation. |

**MVP Proportionality Principle:** For a single-newsroom MVP with low article
volume (FACT: PRD does not specify a volume target — treat as small/medium scale
unless the PRD states otherwise), operational simplicity is a high-priority
driver. An option that requires 3 additional infrastructure services for features
the MVP does not need should be scored accordingly.

---

## 10. Decision Matrix Structure

The decision matrix must:

1. List all options (A through E) as columns.
2. List all 13 drivers (§5) as rows.
3. Score each cell from 1 (poor) to 5 (excellent).
4. Weight Critical drivers (1–3: Operational Simplicity, Python Compatibility,
   PostgreSQL Integration) as 3x; High drivers (4–9) as 2x; Medium drivers
   (10–13) as 1x.
5. No driver may be double-counted.
6. The matrix must not predetermine the outcome; all options must be scored
   before a conclusion is drawn.

---

## 11. Reversibility Analysis (Mandatory Section)

The analysis must assess:

- If Option X is selected and later needs to be replaced, what is the migration cost?
- Which parts of the application are affected by the queue technology choice?
- The domain layer must not import queue primitives (ADR-002 Invariant 7). If
  this is respected, how much of the migration is limited to the infrastructure
  layer?
- Which options are most reversible?

---

## 12. Preliminary Recommendation Structure

After the comparative analysis, the analysis must state a preliminary
recommendation. It must:

1. Name the recommended option explicitly.
2. State the primary reason (the single most important driver or differentiator).
3. State what was rejected and why.
4. State what conditions would change the recommendation.
5. Identify what remains for human decision.

**The preliminary recommendation is not the final decision.** It is technical
guidance for the human decision-maker.

---

## 13. Unknowns Requiring Human Input

The analysis must identify items where:

- Technical evidence is unavailable without external research.
- A business preference (e.g., operations team capabilities) is required.
- The decision depends on a future ADR or specification.

**Known unknowns at briefing time:**

| Unknown | Why It Matters | Needed Before |
| :--- | :--- | :--- |
| PRD article volume target | Determines if a PG-native queue is sufficient or if Redis is needed | Decision |
| Operations team capacity for Redis/broker management | Affects operational complexity scoring | Decision |
| Platform idempotency key availability | Affects publication job design (from ADR-002) | Publication Delivery ADR |
| Authentication ADR (actor identity) | Affects how `actor_id` is set in job-triggered audit records | Auth ADR |
| Deployment environment constraints | Cloud vs. self-hosted affects broker options | Infra ADR |

---

## 14. Explicit Non-Goals for ADR-003

ADR-003 must NOT decide:

| Out of Scope | Belongs To |
| :--- | :--- |
| ORM selection or SQLAlchemy configuration | Data Access Specification |
| Authentication provider | Authentication ADR |
| Cloud provider, Kubernetes, or infrastructure topology | Infrastructure ADR |
| Event Sourcing (closed for MVP by ADR-002) | Closed |
| Microservices decomposition | Architectural evolution |
| Social platform API implementation details | Publication Delivery ADR |
| Monitoring/observability stack (Prometheus, Grafana, etc.) | Observability ADR |
| Specific retry count values and backoff parameters | Implementation / Operations Specification |

---

## 15. Deferred Decisions That ADR-003 Must Acknowledge

The following items are architecturally adjacent but must be deferred:

| Deferred Item | Reason | Owner |
| :--- | :--- | :--- |
| Specific retry count limits per job type | Operational parameter; depends on SLA | Ops Spec |
| Dead-letter queue implementation | Depends on chosen broker | Post-ADR-003 |
| Job monitoring dashboard | Depends on chosen observability stack | Observability ADR |
| Worker autoscaling policy | Depends on deployment environment | Infra ADR |
| Job payload schema versioning | Depends on domain model evolution | Domain Spec |

---

## 16. Required Sections in ADR-003-Analysis.md

The ADR-003 Creator must produce an analysis document with all of the following
sections, in this order:

```
1. Document Metadata
2. Executive Summary
3. Decision Context
4. Authoritative Constraints (inherited from ADR-001 + ADR-002)
5. Workload Characterization (from PRD)
6. Candidate Options (A through E)
   - For each: description, key capabilities, limitations, ADR-002 invariant compatibility
7. Decision Drivers (all 13, non-duplicated)
8. Critical Failure Scenario Analysis (all 8 scenarios × all 5 options)
9. Transactional Outbox Analysis (all 4 patterns)
10. Python Ecosystem Compatibility Analysis
11. Operational Complexity Analysis
12. Decision Matrix (weighted scoring)
13. Reversibility Analysis
14. Preliminary Recommendation
    - Recommended option
    - Primary rationale
    - Rejected options + reason
    - Conditions that would change the recommendation
15. Open Questions for Human Decision
16. Explicit Deferred Decisions
17. References
```

---

## 17. Methodological Requirements (Non-Negotiable)

The ADR-003 Creator must apply the following methodological rules throughout
the analysis:

| Rule | Requirement |
| :--- | :--- |
| Evidence classification | Every empirical claim must be labeled: FACT, INFERENCE, or ASSUMPTION |
| No pre-selection | No option may be selected or eliminated before the decision matrix |
| No double-counting | Each decision driver appears exactly once; no sub-criteria that re-score the same property |
| No circular arguments | Do not use downstream decisions (ORM, cloud) as arguments for upstream choices |
| No popularity bias | "X is widely used" is not a decision driver |
| MVP proportionality | Every feature claim must be weighed against actual PRD requirements |
| Invariant compliance | Every option must be explicitly checked against ADR-002's 7 invariants |
| Separation of concerns | Domain, Application, and Infrastructure boundaries must be respected in all designs |
| Distinction | Clearly separate: business requirements vs. implementation preferences vs. operational convenience |
| No hallucination | Do not invent API capabilities. If a capability is not verified, mark as UNVERIFIED and flag as Open Question |

---

## 18. Status and Next Steps

```
Status: READY FOR ADR-003 ANALYSIS
```

This briefing is a planning artifact. It does not contain the ADR-003 decision
or recommendation.

### Execution Sequence

```
MASTER_BRIEFING_ADR-003_ASYNC_PROCESSING.md (this document)
    ↓
ADR-003-Analysis.md (to be created by the ADR-003 Creator agent)
    ↓
ADR-003-ArchReview.md (Architecture Review)
    ↓
ADR-003-RedTeam.md (if analysis is contested)
    ↓
ADR-003-Reconciliation.md (if required)
    ↓
ADR-003-Decision-Readiness.md
    ↓
HUMAN DECISION
    ↓
ADR-003-AsyncStrategy.md (ACCEPTED)
```

### After Reading This Briefing

The ADR-003 Creator must immediately report:

1. All authoritative artifacts read (checklist).
2. Inherited constraints understood (7 ADR-002 invariants + Constitution requirements).
3. All 5 candidate options identified.
4. All 8 failure scenarios identified.
5. Any gaps or ambiguities in this briefing that require clarification before analysis begins.
