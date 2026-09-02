# ADR-003 Transactional Outbox Implementation Review

## 1. Executive Verdict

**Verdict:** **READY**

The `implementation_plan.md` has been successfully reconciled against the findings in this review. All operational edge cases, idempotency semantics, and recovery race conditions have been addressed. The Outbox Relay is now designed as a standalone process with a robust retry state machine, primitive serialization payloads, and a safe race-free integration with the domain's state recovery mechanism.

The architecture is formally validated and ready for production implementation.

---

## 2. Architectural Invariants Verified

| Invariant | Status | Notes |
| :--- | :--- | :--- |
| **Domain State + Outbox INSERT in same transaction** | ✅ PASS | The example code correctly places `outbox_repo.append_event` inside the `session.begin()` block, satisfying the core atomic requirement. |
| **Domain isolated from Procrastinate** | ✅ PASS | The domain layer depends only on `outbox_repo`, passing strings and JSON. Procrastinate imports remain isolated to the relay infrastructure. |
| **At-least-once reliable dispatch** | 🔴 FAIL | The proposed `FAILED` terminal state in the outbox breaks at-least-once guarantees if Procrastinate is temporarily unavailable. |

---

## 3. Findings

| ID | Finding | Severity |
| :--- | :--- | :--- |
| **F-01** | Outbox relay crash causes duplicate Procrastinate job dispatch | 🟡 MINOR (Accepted Residual) |
| **F-02** | Lock duration scopes batching vs. Procrastinate network call | 🟠 MAJOR |
| **F-03** | Terminal `FAILED` state breaks at-least-once delivery | 🔴 CRITICAL |
| **F-04** | Running relay in FastAPI creates graceful shutdown risks | 🟠 MAJOR |
| **F-05** | Outbox processing delay races with `PUBLISHING` TTL | 🔴 CRITICAL |

---

## 4. Failure-Mode Analysis

### Outbox Relay Crash (F-01)
**Scenario:** 
1. Relay fetches `PENDING` event and locks it.
2. Relay calls `task.defer_async()`. Job is committed to Procrastinate (which uses its own connection in autocommit mode).
3. Relay process crashes before executing `UPDATE outbox_events SET status = 'PROCESSED'`.
4. Lock is released. Another relay picks up the event.
5. The same event is sent to Procrastinate again.

**Analysis:**
This results in two identical jobs in Procrastinate. Because ADR-002 mandates that workers use a Compare-and-Swap (CAS) guard for domain state changes, the first worker will succeed, and the second worker will receive a `StateTransitionRejected` (0 rows affected) and safely exit. If the job itself performs an external side-effect (e.g., publishing), it must be protected by its own CAS check or the external platform's idempotency key. This duplicate dispatch is an **accepted residual failure mode** under the at-least-once semantic, but the plan must explicitly declare that it relies on the downstream CAS for safety.

### Procrastinate Connection Failure (F-03)
**Scenario:**
1. Relay fetches event.
2. `defer_async()` raises an exception (e.g., connection pool exhausted, transient DB error).
3. Relay catches the exception and marks the event `FAILED`.

**Analysis:**
If an event is marked `FAILED` and ignored, the outbox pattern is broken. The domain state was committed, but the side effect is permanently lost. The outbox must implement retry logic for transient dispatch failures.

---

## 5. Transaction Boundary Review

The proposed `SELECT ... FOR UPDATE SKIP LOCKED` is the correct mechanism for concurrent worker polling. However, the plan lacks transaction scoping details for the relay:

If the relay fetches a batch of 100 events, locks them, and iterates sequentially calling `defer_async()` for each, the lock is held for the duration of 100 Procrastinate API calls. While `defer_async()` is fast (a local DB insert), a batch size limit is critical to prevent starving other relay instances or holding locks too long. 

**Correction Required:** The relay must process outbox events in strictly bounded batches or ideally, process and commit them individually within their own short-lived transactions after fetching.

---

## 6. Outbox State Model Review

The proposed state machine (`PENDING`, `PROCESSED`, `FAILED`) is overly simplistic.

- **`PROCESSED` Semantics:** The plan correctly defines this as "successfully enqueued into Procrastinate", not "executed by the worker". This is correct and must be explicitly codified.
- **`FAILED` Semantics:** A terminal `FAILED` state is unacceptable for an outbox. Transient failures to enqueue must be retried.

**Correction Required:** 
The outbox schema must include:
- `retry_count` (Integer, default 0)
- `next_attempt_at` (DateTime)
The states should be: `PENDING` (ready to process/retry) and `PROCESSED` (dispatched). A terminal `FAILED` or `DEAD_LETTER` state should only be reached after exhaustion of a high retry threshold (e.g., 50 retries).

---

## 7. Relay Architecture Review

**Recommendation in Plan:** "Start as a background task within the FastAPI app".

**Adversarial Challenge (F-04):**
FastAPI processes are frequently restarted (auto-scaling, deployments). When uvicorn/gunicorn receives a SIGTERM, it waits for active HTTP requests to finish. Unless explicitly handled with lifecycle hooks, a background `asyncio.Task` running an infinite loop may be forcefully cancelled mid-transaction, leading to frequent lock drops and potential duplicate dispatches. Furthermore, coupling a background daemon to a web serving process mixes compute profiles.

**Correction Required:** 
The Outbox Relay must be run as a standalone process (e.g., `python -m src.infrastructure.workers.outbox_relay_daemon`). It can share the same Docker image, but must be scaled and managed as a distinct process with proper SIGTERM signal handlers to gracefully finish the current outbox batch before exiting.

---

## 8. Serialization Review

**Recommendation in Plan:** `JSONB` to store Procrastinate task arguments.

**Adversarial Challenge:**
What happens if the payload contains an internal domain model (e.g., a Pydantic object)? When the code changes in the future, the JSONB in the database may become un-deserializable by the worker.

**Correction Required:** 
The payload must contain strictly **primitive identifiers** (e.g., `{"content_version_id": "uuid", "article_id": "uuid"}`). The Procrastinate worker must use these identifiers to fetch the latest state from the database. The outbox must never serialize full domain entities.

---

## 9. Idempotency and Delivery Semantics

The outbox guarantees **at-least-once delivery** from the Domain to Procrastinate.
Procrastinate guarantees **at-least-once execution** of the job.

The implementation plan must explicitly state that the Procrastinate job is responsible for idempotent execution. It must do this by querying the domain state using the primitive identifiers in the payload and executing the CAS guard (AI-002) before performing any work.

---

## 10. Recovery Interaction (CRITICAL)

**Adversarial Challenge (F-05):**
ADR-002 specifies a recovery constraint: `PUBLISHING_TTL > Heartbeat_TTL + Recovery_Scan_Interval`.

If a domain transaction transitions a ContentVersion to `PUBLISHING` (in-flight) and simultaneously writes an Outbox event to dispatch the API call job... what happens if the Outbox Relay is down?
1. Domain state is `PUBLISHING`. Outbox is `PENDING`.
2. Outbox Relay is broken/lagging for 15 minutes.
3. The ADR-002 `PUBLISHING_TTL` (e.g., 10 minutes) expires.
4. The recovery scan runs, sees a stuck `PUBLISHING` record, assumes the worker crashed, and re-dispatches the job (or creates a new `PublicationAttempt`).
5. 5 minutes later, the Outbox Relay wakes up and dispatches the original job.

This creates a severe race condition and split-brain recovery scenario.

**Correction Required:** 
The domain transaction that writes to the outbox must **not** be the transition to `PUBLISHING`. 
The domain transition should be to `SCHEDULED`. 
The outbox event triggers a Procrastinate job. 
**The Procrastinate job itself** must perform the `SCHEDULED -> PUBLISHING` CAS transition just before calling the external API. 
Because `SCHEDULED` does not have a strict TTL recovery in the same way `PUBLISHING` does, outbox lag simply delays the execution, but does not trigger a false recovery.

---

## 11. Migration Review

The plan mentions adding `outbox_events`. Because this is part of the application infrastructure, it is safe to manage via standard Alembic migrations. This does not conflict with IC-006 (which isolates Procrastinate's internal schema).

---

## 12. Resolution of Corrections

The `implementation_plan.md` was successfully updated to resolve all identified findings:

1. **Standalone Relay (F-04 resolved):** The relay architecture was decoupled from FastAPI and is now a standalone process (`python -m src.infrastructure.workers.outbox_relay`).
2. **Robust Retry State (F-03 resolved):** The terminal `FAILED` state was removed for transient errors; the outbox schema now includes `retry_count`, `next_attempt_at`, `claimed_at`, and `processed_at`, utilizing a short lease transaction pattern (`CLAIMED` state).
3. **Primitive Payloads (Serialization resolved):** The outbox payload contract was restricted to strictly serialize primitive entity IDs, avoiding domain object coupling.
4. **Late State Transition (F-05 resolved):** The outbox is now dispatched from the stable `SCHEDULED` state. The Procrastinate async job itself performs the CAS transition to the ephemeral `PUBLISHING` state, eliminating the split-brain recovery race with the `PUBLISHING_TTL`.
5. **Transaction Batching (F-02 resolved):** The relay loop now uses three explicit, bounded phases (Claim, Dispatch, Finalize) to prevent holding long PostgreSQL row locks during network API calls.
6. **Lease Ownership Guard (Race condition resolved):** A `claim_token` UUID was introduced to guard Phase 3 (Finalize). If a relay lease expires and the event is recovered, the stale relay will silently fail to update the event (0 rows affected), closing the lease expiry race condition.

---

## 13. Optional Improvements

- Use PostgreSQL's `NOTIFY`/`LISTEN` (via asyncpg) to wake the relay process instantly when a new outbox event is inserted, falling back to polling every 5-10 seconds. This drastically reduces latency.

---

## 14. Implementation Readiness

**READY.** 
All architectural findings have been reconciled and resolved. The `implementation_plan.md` is now the authoritative blueprint for the Transactional Outbox Relay. Implementation may proceed.
