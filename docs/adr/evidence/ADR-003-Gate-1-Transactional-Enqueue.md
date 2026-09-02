# ADR-003 Gate 1 Validation: Transactional Enqueue

## 1. Executive Summary

- **Status:** 🔴 FAILED (Invariant Violation Demonstrated)
- **Tested Hypothesis:** Procrastinate `defer_async()` can participate seamlessly in an existing SQLAlchemy `AsyncSession` transaction when using the native `PsycopgConnector`.
- **Finding:** The dispatched job SURVIVES a rollback of the SQLAlchemy domain transaction. This violates the **Atomic State-to-Audit-to-Event (ASAE)** invariant inherited from `ADR-002`.

## 2. Test Configuration

- **ORM Runtime:** SQLAlchemy 2.0 + `asyncpg` driver (`AsyncSession`)
- **Queue Runtime:** Procrastinate + `psycopg` (v3) driver (`PsycopgConnector`)
- **Database:** PostgreSQL 16 (jinc_gate1)
- **OS:** Windows (running via Python 3.12 with `WindowsSelectorEventLoopPolicy` enforced)

## 3. Empirical Results

The validation script `gate1/run_gate1.py` successfully provisioned the schema and ran the two critical atomicity scenarios.

### Scenario G1-A (Commit Atomicity)
- **Action:** Domain state INSERT + Audit log INSERT + `defer_async()` within `session.begin()`, followed by commit.
- **Expected:** Job is found in `procrastinate_jobs`.
- **Result:** **PASS**. Job was successfully enqueued and domain state was persisted.

### Scenario G1-B (Rollback Atomicity)
- **Action:** Domain state INSERT + Audit log INSERT + `defer_async()` within `session.begin()`, followed by an explicit `raise ValueError("Force Rollback")`.
- **Expected:** The domain state is rolled back (verified: `status IS None`) AND the enqueued job is rolled back (verified: `jobs count == 0`).
- **Result:** **🔴 FAIL**. The domain state rolled back correctly, but the Procrastinate job **survived the rollback and was persisted in the database**.

## 4. Root Cause Analysis

1. **Driver Isolation:** SQLAlchemy uses the `asyncpg` driver, while Procrastinate's async connector requires the `psycopg` driver.
2. **Connection Pools:** Because the drivers are fundamentally different, they cannot share the same underlying TCP connection or database session.
3. **Transaction Boundary Leak:** When `await my_task.defer_async(...)` is called inside the SQLAlchemy transaction block, Procrastinate borrows a connection from its own `psycopg` pool, begins a separate transaction, inserts the job, and commits it independently of the SQLAlchemy `asyncpg` transaction.

## 5. Architectural Conclusion

**Direct Transactional Dispatch (Option A) is impossible** in our stack without writing a custom `AsyncpgConnector` for Procrastinate, which introduces significant maintenance overhead and violates our risk-averse engineering constitution.

To preserve the ASAE invariant, **ADR-003 must mandate the Transactional Outbox Pattern (Option B)**.
- Domain transitions and outbox events will both be inserted via the SQLAlchemy `AsyncSession` (sharing the exact same `asyncpg` connection and transaction).
- A secondary relay/publisher worker will poll the outbox table and issue the `defer_async()` calls to Procrastinate.

Gate 1 is officially closed. ADR-003 may proceed to final acceptance with the Outbox requirement explicitly codified.
