# ADR-003 Red Team Report

# Async Processing, Background Jobs & Workflow Execution

**Status:** Adversarial Red Team — Independent Falsification Review  
**Primary Target:** `docs/adr/ADR-003-Analysis-Revised.md`  
**Review Date:** 2026-09-01  
**Posture:** Maximum adversarial scrutiny. Every claim treated as untrusted until independently verifiable.  
**Objective:** Falsify the architecture. Not improve it.

---

## 1. Executive Verdict

### `HOLDS WITH MATERIAL REVISIONS`

The recommendation of Option A (Procrastinate) is not rejected. It survives the Red Team with the following qualification:

**The primary architectural claim — that the Transactional Dispatch Invariant guarantees S3 prevention — is built on a connection-sharing assumption that is not a library guarantee and is not specified with sufficient precision in the revised analysis.** The invariant is achievable, but it depends on a specific integration pattern that the analysis does not define concretely enough to be enforced.

Two additional findings require mandatory resolution before the Red Team clears the architecture for human decision:

1. **RT-001 (CRITICAL):** The exact Procrastinate + SQLAlchemy async connection-sharing mechanism is unspecified. Without the precise API pattern, the Transactional Dispatch Invariant is a design intention, not an architectural guarantee.

2. **RT-002 (CRITICAL):** Asyncio event loop blocking can cause a live worker to miss heartbeats, triggering Procrastinate's dead-worker recovery while the worker is still executing an external call. The Single Recovery Authority Protocol does not account for this zombie worker scenario. The ordering constraint `PUBLISHING_TTL > Heartbeat_TTL + Scan_Interval` is necessary but not sufficient.

All other findings are MAJOR or MINOR and do not invalidate the core recommendation. Option A remains superior to all alternatives. The architecture requires targeted hardening, not replacement.

---

## 2. Scenario Scorecard

| Scenario | Result | Primary Finding |
| :--- | :---: | :--- |
| T-001: Different connection between SQLAlchemy and Procrastinate | **PARTIAL** | Connection sharing requires explicit implementation; not automatic |
| T-002: Hidden commit in Procrastinate connector | **PASS** (conditional) | SQLAlchemyConnector uses session; autocommit only if misconfigured |
| T-003: defer_async() succeeds, domain transaction fails | **PASS** (conditional) | Rollback propagates correctly if same connection; fails if different |
| T-004: Retry after transient DB error creates duplicate job | **PASS** | Rollback cleans up; retry produces new job; no duplicate |
| T-005: Savepoint/nested transaction anti-pattern | **PARTIAL** | `begin_nested()` inside session.begin() can lose the job |
| S1: Worker crash recovery vs. PUBLISHING scan race | **PARTIAL** | TTL ordering reduces race window but is not deterministic |
| S2: Duplicate execution — CAS defense | **PASS** | CAS prevents double state transition; idempotent exit confirmed |
| S3: Lost dispatch under Procrastinate | **PASS** (conditional) | Prevented only when Transactional Dispatch Invariant correctly implemented |
| S4: Job dispatched, DB transaction rolls back | **PASS** | Rollback propagates; CAS finds no matching state |
| S5: LLM timeout — retry taxonomy collision | **PARTIAL** | Boundary between technical retry and domain recovery is ambiguous for partial commits |
| S6: Publication timeout — duplicate publication | **PASS** (inherent residual) | Procrastinate does not worsen ADR-002 accepted residual risk |
| S7: Scheduler crash with pending publications | **PASS** | PostgreSQL-backed scheduled_at survives; worker restart reclaims |
| S8: Retry storm | **PASS** | Per-queue concurrency limits + RetryStrategy provide adequate protection |
| Zombie worker (asyncio event loop blocking) | **FAIL** | Live worker misses heartbeats → Procrastinate reclaims job → concurrent execution |
| Worker resurrection after partition recovery | **PARTIAL** | Worker A and recovery scenario result in duplicate external dispatch window |
| PostgreSQL outage during transactional enqueue | **PASS** | Transaction rolls back; job does not exist; no stale job |
| PostgreSQL restoration after outage | **PARTIAL** | Job backlog concentration creates pressure; PUBLISHING scan may overfire |
| Celery counterfactual | **PASS** (Celery does not hold) | No MVP condition makes Celery architecturally superior |

---

## 3. Findings

---

### RT-001 🔴 CRITICAL — Connection Sharing Is a Design Intention, Not a Library Guarantee

**Category:** T-001 / Transactional Dispatch Invariant

#### Failure Scenario

```
Initial State: Application uses SQLAlchemy AsyncSession connected to PostgreSQL.
              Procrastinate App initialized with its own AsyncpgConnector at startup.

Event Sequence:
    async with session.begin():
        # SQLAlchemy uses connection C1 from pool P
        await content_version_repo.transition(cv_id, ...)  # Uses C1, in transaction T1
        await generate_task.defer_async(content_version_id=str(cv_id))
        # ↑ Procrastinate uses its own connection C2 from its own pool
        #   C2 is in AUTOCOMMIT mode (asyncpg default for non-transactional connections)
        #   Job INSERT commits immediately on C2
        # domain transaction continues on C1...
        raise ValidationError("late constraint check")
        # T1 rolls back on C1
        # CAS UPDATE rolled back ✅
        # audit INSERT rolled back ✅
        # Procrastinate job INSERT NOT rolled back — committed on C2 ❌

Database State: ContentVersion = GENERATED (rolled back to original state)
Job State:      procrastinate_jobs contains a job for content_version_id that never transitioned
Recovery:       Worker picks up job. CAS: GENERATED → VALIDATED (or whatever expected state).
                If entity was rolled back to GENERATED and job is for GENERATED→VALIDATED, CAS succeeds.
                This is S4 in reverse — a job survives the transaction that created it.
External:       LLM call made for content that may not be in the expected post-CAS state.
Result:         FAIL — S3 prevented on the happy path; S4-reverse created by connection isolation.
```

**Architectural Cause:**

SQLAlchemy's `AsyncSession` manages a connection (e.g., `C1`) obtained from SQLAlchemy's own connection pool. Procrastinate's `AsyncpgConnector` manages connections from a separate pool. Unless Procrastinate is explicitly configured to use the SAME connection as the current SQLAlchemy session, the `defer_async()` call operates on a separate connection with its own transaction lifecycle.

asyncpg connections default to autocommit when not explicitly in a transaction. A Procrastinate `AsyncpgConnector` not participating in a SQLAlchemy-managed transaction will autocommit each INSERT immediately. (FACT — asyncpg documentation; autocommit is the default connection mode in asyncpg unless explicitly enrolled in a transaction)

**The revised analysis (§8.1 Condition 1) states:**

> "The Procrastinate async connector must use the same PostgreSQL connection as the SQLAlchemy session."

This is correct as a requirement. It does not specify the implementation mechanism. The Red Team finds that this mechanism is non-trivial:

Procrastinate provides a `SQLAlchemyConnector` that accepts an SQLAlchemy `Engine`. However, SQLAlchemy's async engine connection pooling means that `SQLAlchemyConnector` and `AsyncSession` may still acquire different connections from the same pool. To guarantee the SAME connection, the `SQLAlchemyConnector` must be initialized per-session, not per-engine, and must be given the session's underlying connection — not the engine.

The correct pattern requires something equivalent to:

```python
async with session.begin():
    # Get the raw asyncpg connection from the current session
    raw_conn = await session.connection()
    # Tell Procrastinate to use this specific connection for this defer call
    # The exact API depends on Procrastinate version and may require:
    # - Using App.open_async(conn=raw_conn)
    # - Or passing connector=... to the defer call
    # This is NOT the standard usage pattern shown in basic Procrastinate examples
```

The exact mechanism requires verification against the current Procrastinate API. (INSUFFICIENT EVIDENCE — the revised analysis states the requirement but not the verified API call)

**Evidence Classification:** FACT (asyncpg autocommit default); INSUFFICIENT EVIDENCE (exact Procrastinate connection-sharing API)

**Is this fixable?** Yes — the fix is to specify the exact connection-sharing pattern in a mandatory implementation specification that accompanies the ADR. The architectural decision remains Option A, but the Transactional Dispatch Invariant requires a verified implementation pattern, not a conceptual requirement.

**Required Remediation:** The reconciliation must include or reference a verified implementation pattern demonstrating Procrastinate + SQLAlchemy async connection sharing in the same transaction. This must be verified against the actual Procrastinate API (not inferred from documentation descriptions). Until verified, the claim that the invariant "guarantees" S3 prevention must be qualified as "achievable when correctly implemented with verified connection sharing."

**Does remediation change the core decision?** No. Even if the transactional integration requires an explicit implementation specification, Option A remains the only candidate that offers this capability. Options B, C, and D cannot participate in the PostgreSQL transaction regardless of implementation effort. The decision outcome is unchanged; the language of the claim requires qualification.

---

### RT-002 🔴 CRITICAL — Asyncio Event Loop Blocking Creates Zombie Worker Scenario

**Category:** Single Recovery Authority Protocol; Worker Resurrection

#### Failure Scenario

```
Initial State: Worker A is executing a Procrastinate job.
               ContentVersion status = PUBLISHING (CAS committed).
               PublicationAttempt A created.
               Procrastinate job status = 'doing'. Heartbeat timer running.

Event Sequence:
    T=0:  Worker A calls external LinkedIn API.
          The API call uses httpx.Client (synchronous) accidentally called
          from within an async function without asyncio.to_thread().
          This blocks the asyncio event loop on Worker A.
    
    T=1:  Worker A's asyncio event loop is BLOCKED.
          All pending coroutines on Worker A are suspended, including:
          - The Procrastinate heartbeat coroutine.
          - Any connection pool keepalive.
    
    T=2:  Procrastinate_Heartbeat_TTL expires.
          The DATABASE observes no heartbeat from Worker A.
          Procrastinate reclaims the job: status 'doing' → 'queued'.
          (Domain state: ContentVersion still = PUBLISHING)
    
    T=3:  Worker B picks up the 'queued' job.
          Worker B executes the use case.
          CAS: SCHEDULED → PUBLISHING returns 0 rows.
          (Entity is already PUBLISHING from T=0)
          Worker B: "entity not in expected state — exit gracefully." Logs idempotent exit.
          Procrastinate marks Worker B's job execution as... 'succeeded'? 'failed'?
          (Depends on whether 0-rows-CAS is handled as success or failure in the use case)
    
    T=4:  Worker A's blocking call completes (LinkedIn responded after a long pause).
          Worker A's event loop unblocks.
          Worker A proceeds to update database:
            UPDATE publication_attempts SET status=SUCCESS, external_id='li_post_123'
            CAS: PUBLISHING → PUBLISHED
          Both succeed. ContentVersion = PUBLISHED. ✅
    
    T=5:  PUBLISHING recovery scan runs (PUBLISHING_TTL > Heartbeat_TTL + Scan_Interval).
          Finds ContentVersion = PUBLISHED. Takes no action. ✅

Database State: PUBLISHED ✅
Job State:      One job completed (Worker A). Worker B's job was an idempotent no-op.
External:       ONE publication on LinkedIn. ✅
Result on happy path: PASS

BUT — alternative T=3:
    T=3b: PUBLISHING_TTL fires BEFORE Worker A unblocks.
           Recovery scan: CAS PUBLISHING → SCHEDULED (succeeds — entity was still PUBLISHING)
           New PublicationAttempt B created.
           Recovery dispatches a new publication job.
    T=3c: Worker B (recovery-dispatched) executes.
           CAS: SCHEDULED → PUBLISHING (succeeds — entity was reset to SCHEDULED)
           Worker B creates PublicationAttempt C.
           Worker B calls LinkedIn API: SUCCESS. external_id='li_post_456'.
           CAS: PUBLISHING → PUBLISHED (succeeds).
           ContentVersion = PUBLISHED ✅
    T=4b: Worker A unblocks. LinkedIn has ALREADY responded.
           Worker A tries: CAS PUBLISHING → PUBLISHED.
           Returns 0 rows (entity is now PUBLISHED, not PUBLISHING).
           Worker A cannot complete its state transition.
           Worker A tries to update PublicationAttempt A: 
             UPDATE publication_attempts SET status=SUCCESS WHERE id=A_id
             This UPDATE succeeds — it's not gated by the ContentVersion status.
           PublicationAttempt A = SUCCESS (but ContentVersion was published via Attempt C).
Result:
    External side effect: TWO LinkedIn posts (li_post_123 and li_post_456). ❌
    Domain state: ContentVersion = PUBLISHED ✅ (via Worker B)
    Audit: Two PublicationAttempts marked SUCCESS — ambiguous audit trail.
    FAIL on external side effects (at-least-once window opened).
    PARTIAL — domain state is consistent; audit is ambiguous.
```

**The Critical Issue — WHY THIS IS SPECIFICALLY A ZOMBIE WORKER RISK:**

The scenario above is the ADR-002 accepted residual risk (at-least-once publication). The question the Red Team must answer is: **does Procrastinate's heartbeat mechanism introduce a UNIQUE duplicate publication window that does not exist in Redis-backed alternatives?**

**Answer: Yes, in one specific way.**

In a Redis-backed queue (ARQ), visibility timeout is managed by the broker. If a worker disappears, the broker re-queues after the visibility timeout. The original worker's job is then at risk if it recovers. This is the SAME scenario.

However, with Procrastinate, there is an additional failure mode: **asyncio event loop blocking does not kill the worker but does kill the heartbeat.** In a Redis-backed queue, if the worker process is alive, it typically sends keep-alives independently of the application event loop (Redis visibility is extended by acking periodically). In Procrastinate, the heartbeat IS an asyncio coroutine — it competes for event loop time. A slow external call (blocking, or simply a very long async call that starves coroutine scheduling) can prevent heartbeat renewal without the worker being dead.

This is uniquely worse for asyncio-based Procrastinate workers than for process-based workers (Celery prefork) or thread-based workers. In a threaded worker, the heartbeat runs on a separate thread and is not blocked by a slow job function.

**Architectural Cause:** Procrastinate's asyncio worker runs all coroutines — including heartbeats — on a single event loop per worker process. Long-running external I/O operations that are not properly awaited (blocking calls, `asyncio.sleep` abuse, very long non-yielding async operations) can starve the heartbeat coroutine. This can cause Procrastinate to declare the worker dead while it is still actively executing an external side effect.

**Evidence Classification:** FACT (asyncio single-threaded event loop; heartbeat is a coroutine competing for loop time); SUPPORTED INFERENCE (blocking call prevents heartbeat without killing process)

**Is this fixable?** Partially. Mitigations:

1. All external calls (HTTP, LLM) must use async libraries (`httpx.AsyncClient`, not `httpx.Client`) — mandatory implementation requirement.
2. Heartbeat interval must be significantly shorter than heartbeat TTL, to tolerate brief event loop pauses.
3. Worker concurrency limits should prevent a single slow job from monopolizing the event loop.
4. Alternatively: heartbeat can run in a separate thread via `asyncio.to_thread` — but this complicates the Procrastinate integration model.

**Does remediation change the core decision?** No. The duplicate publication window is the ADR-002 accepted residual risk. Procrastinate introduces a specific zombie worker variant not present in process-based queues. The required mitigation (async-only external calls) is an implementation constraint that must be added to the mandatory requirements, not a reason to reject Option A. However, the analysis must explicitly acknowledge this as a Procrastinate-specific risk, not just a general at-least-once property.

**Required Remediation:** Add mandatory implementation constraint: "All external I/O operations within Procrastinate task functions must use async-compatible libraries. Synchronous blocking calls within Procrastinate workers are prohibited. Violation creates a zombie worker scenario where the Procrastinate heartbeat fails while the worker executes an external side effect." Additionally, define heartbeat interval ≤ 1/3 of heartbeat TTL to tolerate event loop pauses.

---

### RT-003 🟠 MAJOR — TTL Ordering Constraint Is Probabilistic, Not Deterministic

**Category:** Single Recovery Authority Protocol; §8.2

#### Finding

The Single Recovery Authority Protocol specifies:

```
PUBLISHING_TTL > Procrastinate_Heartbeat_TTL + Recovery_Scan_Interval
```

The Red Team finds that this inequality provides a probabilistic reduction of the recovery race window, not a deterministic elimination of it.

**Failure conditions that violate the ordering without malfunction:**

| Condition | Effect |
| :--- | :--- |
| PostgreSQL load spike | Heartbeat INSERT takes longer; heartbeat_TTL effectively reduced from the DB's perspective |
| Recovery scan jitter | If the scan has ±N seconds of jitter, the actual firing time can be earlier than expected |
| Clock skew between worker and DB | Heartbeat timestamps from the worker's clock vs. TTL evaluation on the DB's clock |
| Scan overrun | If the recovery scan itself is slow (large table), it may run longer than Scan_Interval, effectively reducing the gap |
| `asyncio.sleep` drift in the scan loop | In asyncio, `asyncio.sleep(interval)` is not a hard real-time guarantee |

**Concrete Attack Trace:**

```
Configured values:
  Procrastinate_Heartbeat_TTL = 30s
  Recovery_Scan_Interval = 60s
  PUBLISHING_TTL = 120s (satisfies: 120 > 30 + 60 ✅)

Actual behavior under DB load:
  T=0:  Worker A: SCHEDULED → PUBLISHING. Job = 'doing'.
  T=5:  Worker A crashes. Last heartbeat at T=0.
  T=30: Heartbeat_TTL expires (DB-side, based on DB clock).
         Procrastinate job: 'doing' → 'queued'. ✅ (fires correctly)
  T=32: Worker B picks up job. CAS SCHEDULED→PUBLISHING: 0 rows.
         Worker B exits gracefully. Job marked as failed/succeeded (ambiguous).
  T=120: PUBLISHING_TTL scan fires.
          CAS PUBLISHING → SCHEDULED (succeeds). Recovery PublicationAttempt created.
          Recovery dispatches new job. ✅

But if DB is under load:
  T=0:  Worker A: SCHEDULED → PUBLISHING.
  T=5:  Worker A crashes.
  T=35: Heartbeat_TTL: Worker A missed 2 heartbeat windows. DB detects at T=35 (5s load delay).
         Procrastinate job: 'queued'. ✅
  T=50: PUBLISHING scan runs (30s late due to scan overrun from large table).
         Scan fires at T=50. PUBLISHING entity is 50s old. TTL=120s. Not yet expired. ✅
         Scan takes no action on this entity.
  T=90: Worker B picks up re-queued Procrastinate job.
         CAS SCHEDULED→PUBLISHING: 0 rows (entity still PUBLISHING). Worker B exits.
  T=120: PUBLISHING scan fires again. TTL expired.
          Recovery: CAS PUBLISHING→SCHEDULED (succeeds). New PublicationAttempt. Dispatch.
```

In the load-delay scenario, the system is still correct — the PUBLISHING_TTL ordering was not violated in a way that caused concurrent recovery. The delay shifted all timers proportionally.

**However — the critical adversarial scenario:**

```
  T=0:  Worker A: SCHEDULED → PUBLISHING.
  T=5:  Worker A: Event loop blocked (slow blocking LLM call — RT-002).
         Heartbeat coroutine suspended.
  T=30: Heartbeat_TTL fires (DB-side). Job: 'queued'.
  T=35: Worker B picks up job. CAS: 0 rows (PUBLISHING). Exits.
  T=90: PUBLISHING scan fires (normal timing).
         CAS PUBLISHING → SCHEDULED (succeeds).
         Recovery PublicationAttempt created.
         New job dispatched.
  T=95: Worker A's blocking call returns. Worker A unblocks.
         Worker A: tries CAS PUBLISHING → PUBLISHED.
         Entity is now SCHEDULED (reset by scan at T=90).
         CAS returns 0 rows.
         Worker A: "entity no longer in PUBLISHING — cannot complete."
         Worker A: updates PublicationAttempt A to FAILED? SUCCESS? Neither is correct.
         (The LinkedIn API may have responded successfully — Worker A doesn't know what to do)
```

The system behavior at T=95 is underspecified. Worker A received a response from LinkedIn (success or failure). The entity has been reset. Worker A cannot record the outcome against ContentVersion (wrong state). The LinkedInPost may exist on the platform. There is no mechanism to record this outcome against a canonical PublicationAttempt that the system considers authoritative.

**This is a genuine correctness gap.** The revised analysis's Single Recovery Authority Protocol says "Worker A tries CAS PUBLISHING→PUBLISHED; returns 0 rows; exits gracefully." But it does NOT address what Worker A should do with the LinkedIn response it received. The post may be live on LinkedIn. Worker A cannot update the ContentVersion. PublicationAttempt A is in limbo.

**Evidence Classification:** SUPPORTED INFERENCE (based on asyncio single-threaded event loop behavior and PostgreSQL TTL mechanics)

**Fixable?** Partially. The system correctly prevents double domain state commitment (CAS). The audit trail ambiguity (Worker A has a response from LinkedIn but cannot record it) requires:

1. Worker A must attempt to write the external_publication_id to PublicationAttempt A regardless of domain state (UPDATE publication_attempts SET external_id=... WHERE id=A_id is not gated by ContentVersion status).
2. A monitoring alert for "PublicationAttempt with external_id but ContentVersion not PUBLISHED" — indicates a resurrection scenario that needs human review.

---

### RT-004 🟠 MAJOR — Savepoint Anti-Pattern Can Silently Drop the Job

**Category:** T-005 / Transactional Dispatch Invariant

#### Failure Scenario

```
Initial State: Developer uses SQLAlchemy nested transaction (SAVEPOINT) for error isolation.

Event Sequence:
    async with session.begin() as outer_tx:
        await content_version_repo.transition(cv_id, 'GENERATED', 'VALIDATED')  # Outer
        
        async with session.begin_nested() as savepoint:  # Creates SAVEPOINT sp1
            # Some operation that might fail
            await generate_task.defer_async(content_version_id=str(cv_id))  # Inside savepoint
            # ... some other operation
            raise SomeNonDBError("domain validation failed")
            # SAVEPOINT sp1 is rolled back: defer_async() INSERT is rolled back
        
        # Developer catches the error, outer transaction continues
        # ContentVersion transition COMMITTED (outer tx)
        # Procrastinate job INSERT ROLLED BACK (savepoint)

Database State: ContentVersion = VALIDATED (committed in outer tx)
Job State:      No job in procrastinate_jobs
Recovery:       S3 occurs. Entity stuck in VALIDATED indefinitely.
External:       None — no job, no LLM call.
Result:         FAIL — S3 occurs despite Procrastinate being selected.
```

**Architectural Cause:** SQLAlchemy's `begin_nested()` creates a PostgreSQL SAVEPOINT. Any DML (including Procrastinate's job INSERT via defer_async) executed within the savepoint scope is rolled back when the savepoint is rolled back. If the outer transaction commits without catching this, the domain state change is committed but the job is lost.

This failure mode is more likely in complex use cases with multiple steps, error handling, and retry logic — precisely the kind of use cases the JincSAE pipeline will have for multi-platform generation.

**Evidence Classification:** FACT (PostgreSQL SAVEPOINT behavior; SQLAlchemy `begin_nested()` creates SAVEPOINT)

**Fixable?** Yes — with a strict rule: `defer_async()` must NEVER be called inside a `begin_nested()` context. It must always be at the outermost `session.begin()` level. This is a code review gate requirement.

---

### RT-005 🟠 MAJOR — Retry Taxonomy Boundary: Technical Retry vs. Domain Recovery Collision

**Category:** Retry Taxonomy; §9

#### Attack

The revised analysis defines:

- Type 1: Technical retry (LLM infra) — no content committed, retry HTTP call
- Type 4: Publication domain recovery — PUBLISHING TTL exceeded, new PublicationAttempt

**The collision scenario:**

```
T=0:  Worker A: LLM call starts. ContentVersion status = GENERATING (hypothetical in-progress state)
      OR: ContentVersion status = VALIDATED (LLM call pending, no in-progress state defined)

T=5:  LLM call in-flight. Procrastinate retries the job after 30s timeout.

T=30: Procrastinate technical retry fires.
      Worker B picks up the job.
      ContentVersion status = VALIDATED (original state — no CAS was done before LLM call)
      Worker B: calls LLM again.

T=35: LLM returns content to Worker A (from T=0 call).
      Worker A: tries to commit ContentVersion generation result.
      CAS: VALIDATED → GENERATED (or VALIDATED → VALIDATING?)

Q: Is there a defined "LLM call in progress" state for ContentVersion?
```

The SDD and ADR-002 define the state machine as:
`GENERATED → VALIDATED → PENDING_REVIEW → APPROVED → SCHEDULED → PUBLISHING → PUBLISHED`

There is no state between `VALIDATED` and `GENERATED` that represents "LLM call in progress."

This means that when Worker A starts an LLM call, the ContentVersion remains in `VALIDATED`. When Procrastinate retries (Type 1 technical retry), Worker B also finds the ContentVersion in `VALIDATED` and makes a second LLM call. BOTH calls may succeed and attempt to commit their results. The CAS from the first committer succeeds; the second CAS returns 0 rows.

But: the LLM was called TWICE. If LLM calls are metered or expensive, this is a cost concern. If LLM providers impose rate limits, this is a reliability concern. If the LLM generates materially different content on each call (non-deterministic), the first committer's result is accepted and the second is discarded — editorial consistency is preserved, but two generations occurred.

**This is not a correctness failure** (CAS handles it). **It is a cost and rate-limit concern** that the analysis does not surface. The retry policy for LLM jobs must account for this: if the LLM call takes 45s and the Procrastinate retry timeout is 30s, every LLM call will be duplicated.

**Evidence Classification:** SUPPORTED INFERENCE from state machine design and Procrastinate retry behavior

**Fixable?** Yes — by setting LLM job retry timeouts significantly longer than the expected LLM response time (e.g., 5× the p95 LLM latency). This is an implementation parameter, but it must be explicitly specified as a requirement.

---

### RT-006 🟠 MAJOR — PostgreSQL Restoration After Outage: Job Backlog Amplification

**Category:** PostgreSQL Availability; P-005

#### Failure Scenario

```
T=0:  PostgreSQL outage begins.
      All workers lose DB connectivity.
      All Procrastinate LISTEN/NOTIFY connections drop.
      Workers attempting in-flight jobs fail their DB writes.
      procrastinate_jobs table inaccessible.

T=Outage_Duration: PostgreSQL recovers.

T=Recovery+ε: All workers reconnect.
              All pending jobs in procrastinate_jobs become visible simultaneously.
              Workers immediately begin polling/receiving NOTIFY events.
              All queued jobs (accumulated during outage) attempt to execute concurrently.
              Each job execution requires a DB transaction (CAS + audit INSERT).
              Sudden large number of concurrent DB transactions = connection pool saturation.
              PostgreSQL may receive more connections than max_connections allows.
```

**For the JincSAE MVP (low job volume), this is likely not a material concern.** But the analysis accepts coupled availability without noting that recovery-after-outage creates a backlog concentration event.

**For publication-timed jobs specifically:** If an outage lasts 2 hours, all scheduled publications during that window are now overdue. They will all attempt to execute simultaneously upon recovery. CAS prevents double execution, but the burst of DB activity and external API calls (publication retries) may exceed the per-queue concurrency limits.

**Evidence Classification:** SUPPORTED INFERENCE from queue mechanics and PostgreSQL connection behavior

**Fixable?** Yes — per-queue concurrency limits in Procrastinate (already specified in the analysis) bound the burst. This is an existing mitigation. The finding is that the analysis does not acknowledge this recovery burst behavior explicitly.

---

### RT-007 🟡 MINOR — Procrastinate Schema Version Migration During Rolling Deployment

**Category:** Migration Attack; §12.3

#### Finding

The revised analysis (§12.3) correctly identifies Alembic autogenerate contamination and provides the `include_name` mitigation. It does not address rolling deployment with mixed Procrastinate versions.

**Scenario:**

- Application v1.0 runs Procrastinate v2.2
- Application v1.1 requires Procrastinate v2.3 (new schema migration)
- Rolling deployment: some pods run v1.0, some run v1.1
- Procrastinate v2.3 schema migration applied
- v1.0 workers read the updated `procrastinate_jobs` table with the new schema
- If the schema is backward-compatible, v1.0 workers continue correctly
- If the schema is NOT backward-compatible, v1.0 workers fail to read the job table

**Evidence Classification:** ASSUMPTION (Procrastinate's schema compatibility policy between minor versions is not verified)

**This is a deployment operations concern, not a fundamental architectural issue.** The Alembic isolation mitigation (§12.3) is correct; the Procrastinate upgrade procedure must verify schema compatibility before deployment.

---

### RT-008 🟡 MINOR — CAS "0 Rows = Graceful Exit" Is an Application Contract, Not a Framework Guarantee

**Category:** CAS coordination; all scenarios

#### Finding

The analysis repeatedly states: "CAS returns 0 rows → worker exits gracefully."

This is correct behavior IF the application correctly implements this check. The framework (Procrastinate) does not enforce it. A developer who does not check `rows_affected` will not notice the CAS rejection and will proceed with subsequent operations as if the state transition succeeded.

**Example of incorrect implementation:**

```python
async def publish_content(content_version_id: str) -> None:
    # BUG: not checking CAS result
    await session.execute(
        text(
            "UPDATE content_versions SET status = 'PUBLISHING' WHERE id = :id AND status = 'SCHEDULED'"
        ),
        {"id": content_version_id},
    )
    # Developer forgot: if rows_affected == 0, stop here
    # Continues to create PublicationAttempt regardless
    await session.execute(text("INSERT INTO publication_attempts ..."), {...})
    # External API call made even if CAS failed
```

**Evidence Classification:** FACT (Python does not enforce return value checking; SQLAlchemy's `result.rowcount` is not automatically validated)

**Fixable?** Yes — via Repository pattern where the transition method raises a `StateTransitionError` if `rowcount == 0`, ensuring all callers handle the rejection. The analysis should specify this as a mandatory Repository interface contract.

---

### RT-009 🟡 MINOR — ARQ Scores 2 on Retry Semantics: Evidence Should Be Explicit

**Category:** Decision Matrix; Driver 5 for ARQ

#### Finding

The Red Team attempted to verify that ARQ lacks native exponential backoff with jitter. Confirming: ARQ's retry mechanism uses `retry_after` (a flat delay) and `max_tries` (total attempt count). There is no `RetryStrategy` class equivalent to Procrastinate's. Implementing exponential backoff requires the task function to catch exceptions and set its own retry delay. (FACT — ARQ source code and documentation)

Given the Engineering Constitution §15 (No Silent Failure) and the retry storm scenario (S8), ARQ's retry limitation is a real architectural gap for the JincSAE publication pipeline. Score of 2 for Driver 5 is correct.

The Red Team confirms this finding is factual, not inferred. ARQ's score does not need revision.

---

## 4. Claims That Survived Red Team Adversarial Attack

The following architectural claims from `ADR-003-Analysis-Revised.md` were subjected to adversarial scrutiny and **could not be falsified**:

| # | Claim | Verdict |
| :--- | :--- | :--- |
| 1 | "Procrastinate is the only candidate offering transactional job enqueue" | ✅ SURVIVES — all other options (ARQ, TaskIQ, Celery, Temporal) use separate brokers |
| 2 | "CAS prevents double domain state commitment" | ✅ SURVIVES — PostgreSQL CAS is deterministic; cannot commit same transition twice |
| 3 | "RQ is eliminated due to synchronous worker model" | ✅ SURVIVES — RQ's worker model is fundamentally incompatible with asyncio |
| 4 | "Celery's primary rejection is Driver 3 (PG transaction integration)" | ✅ SURVIVES — no Celery mechanism enqueues within a PostgreSQL transaction (see Celery Counterfactual below) |
| 5 | "Option A requires zero additional infrastructure services" | ✅ SURVIVES — Procrastinate requires only PostgreSQL, which is already required by ADR-002 |
| 6 | "Procrastinate periodic tasks are deduplicated via `procrastinate_periodic_defers`" | ✅ SURVIVES — confirmed in Procrastinate documentation; DB locking prevents duplicate periodic execution |
| 7 | "Scheduler crash recovery is superior under Option A because scheduled_at is in PostgreSQL" | ✅ SURVIVES — ARQ's sorted set in Redis is subject to the documented durability concern |
| 8 | "Procrastinate's duplicate publication risk is not worse than ADR-002's accepted residual" | ✅ SURVIVES — the at-least-once window exists for all queue options; Procrastinate does not introduce additional windows beyond the RT-002 zombie worker scenario (which is acknowledged as a Procrastinate-specific risk requiring mitigation) |
| 9 | "Option D (Temporal) fails MVP proportionality" | ✅ SURVIVES — see Celery Counterfactual section; same argument applies to Temporal |
| 10 | "RetryStrategy in Procrastinate provides native exponential backoff with jitter" | ✅ SURVIVES — Procrastinate documentation confirms `RetryStrategy` with configurable intervals and jitter |

---

## 5. Celery Counterfactual — When Would Celery Be Superior?

**Question:** Under what conditions would Celery be architecturally superior for JincSAE?

**Conditions under which Celery would be superior:**

| Condition | Required for Celery advantage |
| :--- | :--- |
| High job throughput (thousands of jobs/hour) | PostgreSQL job table becomes a bottleneck; Redis-backed broker scales better |
| Multi-service distributed task routing | Celery supports routing to different worker pools; Procrastinate does not (single PG) |
| Team with existing Celery operational expertise | Lower operational learning curve |
| Redis already deployed for other purposes | Marginal infrastructure cost of adding Celery broker ≈ 0 |
| Requirement for multiple independent task queues on different brokers | Celery's pluggable broker architecture allows this |

**Do these conditions exist for JincSAE MVP?**

- High throughput: No — PRD specifies no volume target; MVP assumed low double digits/day. (FACT — PRD examined)
- Multi-service distributed routing: No — JincSAE is a single Python service. (FACT — SDD §2)
- Existing Celery/Redis expertise: Unknown — not specified in PRD. (UNKNOWN — but even if true, does not override Driver 3 architectural gap)
- Redis already deployed: No — no ADR has introduced Redis. (FACT — no accepted ADR requires Redis)
- Multiple independent broker queues: No — JincSAE has a single pipeline. (FACT — PRD §1)

**At what point after MVP might Celery become competitive?**

If JincSAE grows to a multi-tenant SaaS serving multiple news organizations, with hundreds of articles per day across dozens of organizations, the PostgreSQL job table would begin to show contention (INFERENCE — estimated threshold: ~500-1000 jobs/hour sustained). At that point, a Redis-backed broker would be architecturally justified. The correct migration path would be Option A → TaskIQ (not Celery), because TaskIQ's asyncio-native model is compatible with the established architecture and provides a lower migration cost.

**Conclusion:** No current or foreseeable-MVP condition makes Celery architecturally superior to Procrastinate for JincSAE. The rejection stands on Driver 3 grounds. The Celery counterfactual does not alter the recommendation.

---

## 6. Worker Resurrection — Complete Attack Analysis

### Full Worst-Case Resurrection Trace

```
Initial State:
  ContentVersion cv_001: status = APPROVED
  No active Procrastinate job for cv_001

T=0: Scheduler claims cv_001.
     CAS APPROVED → SCHEDULED [committed].
     Procrastinate job J1 created for cv_001 [same tx — Transactional Dispatch Invariant].
     
T=1: Worker A picks up J1.
     CAS SCHEDULED → PUBLISHING [committed].
     PublicationAttempt PA_1 created (status=IN_PROGRESS) [same tx].
     Procrastinate J1: status='doing'.
     
T=2: Worker A calls LinkedIn API.
     LinkedIn API: slow response (45s timeout configured).
     
T=3: Worker A's event loop blocked (RT-002 scenario: synchronous call).
     Heartbeat coroutine suspended.
     
T=30: Heartbeat_TTL expires. Procrastinate: J1 status='queued'.
       ContentVersion cv_001: status=PUBLISHING (unchanged — domain tx is separate).
       
T=31: Worker B picks up J1.
      B executes: CAS SCHEDULED → PUBLISHING. Returns 0 rows (entity is PUBLISHING).
      Worker B: exits gracefully. J1 marked as 'failed' in procrastinate_jobs.
      
T=47: Worker A's blocking call returns. LinkedIn: HTTP 200. external_id='li_123'.
      Worker A resumes event loop.
      Worker A: UPDATE PA_1 SET status=SUCCESS, external_id='li_123'. ✅ (no status gate)
      Worker A: CAS PUBLISHING → PUBLISHED. 
      
Q: Is the entity still PUBLISHING at T=47?

CASE I — PUBLISHING_TTL not yet expired:
  ContentVersion: PUBLISHING. CAS succeeds. ContentVersion = PUBLISHED.
  J1: already 'failed' in procrastinate_jobs. Worker A's job was reclaimed.
  Worker A successfully committed its result to an already-reclaimed job.
  Database State: PUBLISHED ✅, PA_1 = SUCCESS ✅.
  External: ONE LinkedIn post ✅.
  PASS.

CASE II — PUBLISHING_TTL expired between T=31 and T=47:
  T=40: PUBLISHING scan runs. CAS PUBLISHING → SCHEDULED. PA_2 created (is_recovery=true).
         New Procrastinate job J2 dispatched.
  T=41: Worker C picks up J2.
         CAS SCHEDULED → PUBLISHING. SUCCEEDS.
         PA_3 created.
         Worker C calls LinkedIn API.
         LinkedIn: HTTP 200 at T=43. external_id='li_456'. [SECOND POST ON LINKEDIN]
         CAS PUBLISHING → PUBLISHED. SUCCEEDS.
         ContentVersion = PUBLISHED.
  T=47: Worker A resumes.
         Worker A: UPDATE PA_1 SET status=SUCCESS, external_id='li_123'. ✅ (UPDATE succeeds — no CV status gate)
         Worker A: CAS PUBLISHING → PUBLISHED. Returns 0 rows (PUBLISHED, not PUBLISHING).
         Worker A cannot complete domain transition.
  
  Database State:
    ContentVersion: PUBLISHED (via Worker C) ✅
    PA_1: status=SUCCESS, external_id='li_123' (Worker A's original attempt) ✅
    PA_2: is_recovery=true (scan-created) 
    PA_3: status=SUCCESS, external_id='li_456' (Worker C's attempt) ✅
  
  External: TWO LinkedIn posts: li_123 AND li_456 ❌ (duplicate publication)
  Audit: Two PublicationAttempts with SUCCESS and different external_ids — ambiguous
  
  Result: FAIL on external side effects.
          PASS on domain state consistency.
          PARTIAL overall.
```

### Key Conclusion from Resurrection Analysis

**CAS prevents double domain state commitment.** Worker A cannot mark the ContentVersion as PUBLISHED twice. CAS is sufficient for domain consistency.

**CAS does NOT prevent the external API call from executing after recovery.** Worker A's LinkedIn call completed at T=47 after the recovery scan had already initiated a new publication chain. The external API cannot be undone.

**This is the ADR-002 formally accepted residual risk.** It is not a new failure mode introduced by Procrastinate. The question is whether Procrastinate worsens this risk compared to alternatives.

**RT-002's contribution:** The zombie worker scenario (event loop blocking) can extend the window during which Worker A is "alive but DB-dead" significantly beyond what a process-based worker (Celery prefork) would experience. A Celery prefork worker that calls a blocking function does not block the heartbeat (different process/thread). This means the zombie window is uniquely larger for Procrastinate asyncio workers when blocking calls are made. The mitigation (async-only external I/O) is a mandatory implementation constraint.

---

## 7. Recovery Authority Attack — Authority Map

| Failure Condition | Authority | Allowed Action | Risk of Competing Action |
| :--- | :--- | :--- | :--- |
| Procrastinate heartbeat expires, entity = PUBLISHING | Procrastinate | Re-queue Procrastinate job | LOW — PUBLISHING entity; new worker's CAS will return 0 rows if entity is PUBLISHING |
| Procrastinate job = 'queued', entity = PUBLISHING, no worker | None (gap) | Neither authority acts until: (a) a new worker picks up the queued job and fails CAS, (b) PUBLISHING TTL fires | MEDIUM — this gap state is underspecified in the protocol |
| PUBLISHING_TTL exceeded, no Procrastinate job | ADR-002 Recovery Scan | CAS PUBLISHING→SCHEDULED + new PA | LOW — CAS guard |
| PUBLISHING_TTL exceeded, Procrastinate job = 'doing' (zombie) | ADR-002 Recovery Scan AND Procrastinate (both fire) | Both act: scan resets PUBLISHING, heartbeat re-queues job | HIGH — competing actions; RT-003 scenario |
| Worker A resurfaces after partition | Worker A (stale) | CAS PUBLISHING→PUBLISHED (may return 0 rows if state changed) | MEDIUM — domain state safe; external side effect already executed |
| PG outage during recovery | None | All recovery suspended | LOW (outage must end before recovery resumes) |
| External API succeeds, response lost | Worker A (stale) AND Recovery Scan | Both may re-dispatch | HIGH — at-least-once window per ADR-002 Decision 2 |

**Finding:** The table above reveals an underspecified gap state: when Procrastinate job is 'queued' (re-queued by heartbeat expiry) but the entity is PUBLISHING, there is a period where no mechanism is actively driving recovery. The new worker (picking up the re-queued job) will fail CAS and exit. The PUBLISHING scan must then fire to drive the entity forward. This gap state is acceptable (the PUBLISHING scan will handle it) but must be documented.

**Is authority genuinely singular?** No — under the zombie worker scenario (RT-002), the Procrastinate heartbeat mechanism and the ADR-002 PUBLISHING scan can both be active simultaneously. CAS serializes their domain effects, but both may take action in overlapping windows. Authority is CAS-serialized, not exclusive by design.

**This does not render the architecture incorrect.** CAS is sufficient for correctness. The analysis should characterize the protocol as "CAS-serialized, not exclusive-authority" — a more accurate description of the actual behavior.

---

## 8. Revised Recommendation

### Keep Option A with Mandatory Revisions

**Option A (Procrastinate) is not rejected.** The fundamental architectural advantage — ability to enqueue jobs within a PostgreSQL transaction — is unique among the evaluated candidates and remains the strongest architectural claim.

**Mandatory revisions before architecture is cleared for human decision:**

### R-001 (from RT-001) — Verify and Specify Connection-Sharing API

The reconciliation must include or reference a verified implementation specification demonstrating the exact Procrastinate API calls required for connection sharing with SQLAlchemy async. This specification must be tested in an integration test before the ADR is accepted. The invariant language must be updated to reference the verified pattern.

**Revised invariant language:**
> "The Transactional Dispatch Invariant is achievable when Procrastinate is configured to use the same underlying database connection as the SQLAlchemy AsyncSession. The exact configuration requires [VERIFIED API PATTERN]. Absence of this configuration produces a separate-connection failure mode equivalent to the dual-write problem. This pattern must be verified by integration test and enforced by code review."

### R-002 (from RT-002) — Define Async-Only External I/O Requirement

Add mandatory implementation constraint:
> "All external I/O operations within Procrastinate task functions must use async-compatible libraries (e.g., `httpx.AsyncClient`, not `httpx.Client`; async LLM SDK clients). Synchronous blocking calls within Procrastinate workers are prohibited. Violation creates a zombie worker scenario (event loop blocked; heartbeat suspended; Procrastinate reclaims job while worker executes external side effect). Heartbeat interval must be set to ≤ 1/3 of heartbeat TTL."

### R-003 (from RT-004) — Prohibit defer_async() Inside begin_nested()

Add mandatory implementation constraint:
> "`defer_async()` must never be called inside a `session.begin_nested()` (SAVEPOINT) scope. The defer call must execute at the outermost `session.begin()` level. Calling defer inside a savepoint that is later rolled back while the outer transaction commits produces a silent S3 (lost dispatch)."

### R-004 (from RT-003) — Qualify PUBLISHING_TTL Ordering as Probabilistic

Revise §8.2 Single Recovery Authority Protocol:
> "The TTL ordering constraint PUBLISHING_TTL > Heartbeat_TTL + Scan_Interval provides a high-probability reduction of the concurrent-recovery window under normal conditions. It is not a deterministic guarantee under adversarial conditions (DB load spikes, asyncio event loop blocking, clock skew). Under the zombie worker scenario (RT-002), the ordering may be violated. The primary correctness guarantee is CAS serialization, not exclusive authority by timeout ordering."

### R-005 (from RT-005) — Define Maximum LLM Job Retry Timeout

Add implementation parameter:
> "LLM generation job retry timeout must be set to ≥ 3× the p95 LLM response latency to prevent duplicate LLM calls from concurrent technical retries. This value must be defined in the Operations Specification."

### R-006 (from RT-008) — Mandate Repository CAS Contract

> "The Repository interface for state transitions must raise `StateTransitionRejected` (or equivalent) when `rowcount == 0`. Task functions must not proceed with external side effects if a `StateTransitionRejected` exception is raised. This is a mandatory Repository interface contract, not an optional implementation detail."

---

*This document is a Red Team adversarial review. It does not make a final human decision. It does not mark ADR-003 as Accepted. The next phase is ADR-003 Reconciliation / Final Decision Brief.*

*Verdict: `HOLDS WITH MATERIAL REVISIONS`*
