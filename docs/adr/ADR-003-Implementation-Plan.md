# Transactional Outbox Pattern Implementation Plan

This document outlines the architectural and code implementation design for the Transactional Outbox Pattern. It serves as the definitive engineering plan to prevent the "Lost Dispatch" failure mode in JincSAE, reconciling findings from the ADR-003 Implementation Review.

## 1. Architectural Sequence & State Machine

The outbox guarantees **at-least-once delivery with bounded retry and terminal operational failure** of an asynchronous job request to Procrastinate without risking a split-brain recovery race with the domain's `PUBLISHING_TTL`.

### The Sequence

```text
APPROVED (or other domain state)
   │
   │ [Domain Transaction]
   │ 1. CAS: APPROVED -> SCHEDULED
   │ 2. Audit: INSERT content_version_transitions
   │ 3. Outbox: INSERT outbox_events (status=PENDING)
   ▼
SCHEDULED (Stable Domain State)
   │
   │ [Outbox Relay - Separate Process]
   │ 4. T1: Claim (FOR UPDATE SKIP LOCKED) -> status=CLAIMED
   │ 5. defer_async() (Procrastinate Autocommit)
   │ 6. T2: Finalize -> status=PROCESSED
   ▼
Procrastinate Job Enqueued
   │
   │ [Procrastinate Worker]
   │ 7. T3: CAS: SCHEDULED -> PUBLISHING
   │ 8. Audit: INSERT transitions
   │ 9. INSERT PublicationAttempt
   ▼
PUBLISHING (In-Flight Domain State)
   │
   │ 10. External API Call (LinkedIn, etc.)
   ▼
External Social API
```

**Consistency Verification:**
Because the outbox event is emitted when the domain transitions to `SCHEDULED`, any delay or crash in the Outbox Relay simply delays the external publication. It **does not** trigger the ADR-002 `PUBLISHING_TTL` recovery scan, because the entity is not yet in the `PUBLISHING` state. The ephemeral `PUBLISHING` state (and its strict TTL) only begins when the Procrastinate worker actively picks up the job and executes the CAS guard.

## 2. Duplicate Job Dispatch & Idempotency

**Scenario: Outbox Relay Crash**
If the relay claims an event, successfully calls `defer_async()`, and then crashes before completing Transaction 2 (Finalization), the outbox event remains stuck in `CLAIMED`. A recovery scan will revert it to `PENDING`, and another relay will dispatch it again, creating a **duplicate job in Procrastinate**.

**Safety Guarantee:**
When both Procrastinate jobs execute, they will query the database and attempt step 7 (`CAS: SCHEDULED -> PUBLISHING`).

- **Worker 1:** CAS succeeds (`rows_affected == 1`). Proceeds to call the external API.
- **Worker 2:** CAS fails (`rows_affected == 0`, because state is now `PUBLISHING`). Worker raises `StateTransitionRejected` and exits safely without calling the external API.

This formally guarantees domain consistency. The residual risk of a duplicate publication relies solely on the extremely narrow window of a worker crash *after* the CAS but *before* completing the external API call (accepted in ADR-002). The Outbox does not introduce new exactly-once guarantees, nor does it weaken the accepted at-least-once semantics.

## 3. Database Schema: Outbox State Model

#### `src/infrastructure/database/models/outbox.py`

```python
class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    # States: PENDING, CLAIMED, PROCESSED, FAILED

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[UUID] = mapped_column(nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
```

**State Semantics:**

- `PENDING`: Ready for dispatch. `next_attempt_at <= NOW()`.
- `CLAIMED`: Locked by a relay worker with a unique `claim_token`. Awaits dispatch confirmation.
- `PROCESSED`: Terminal success. Successfully handed off to Procrastinate.
- `FAILED`: Terminal operational failure to dispatch the outbox event. Reached maximum retry count (e.g., 50) without successfully reaching Procrastinate. This strictly signifies an infrastructure failure, *not* that the `PublicationAttempt` failed or that the external social API rejected the publication.

## 4. Transactional Boundaries, Locking & Lease Ownership

To prevent holding PostgreSQL row locks during network API calls, the relay uses three distinct phases guarded by explicit ownership tokens (`claim_token`). This prevents stale workers from finalizing events that have been reclaimed by recovery.

**Architectural Timeout Rules:**
To avoid lease expiry during valid processing, the architecture enforces:

- Explicit dispatch timeout for `defer_async()` (e.g., 5 seconds per event).
- Max processing time per batch = `batch_size` * `dispatch_timeout`.
- `Lease TTL` > `Max processing time per batch` + `Safety Margin`.
For MVP: Batch size = 50. Dispatch timeout = 2s. Max batch time = 100s. Lease TTL = 3 minutes.

### Phase 1: Claim (Short Transaction)

```sql
BEGIN;
SELECT id FROM outbox_events 
WHERE status = 'PENDING' AND next_attempt_at <= NOW()
FOR UPDATE SKIP LOCKED LIMIT 50;

UPDATE outbox_events 
SET status = 'CLAIMED', 
    claimed_at = NOW(), 
    claim_token = :generated_uuid,
    attempt_count = attempt_count + 1
WHERE id IN (<selected_ids>)
RETURNING *;
COMMIT;
```

### Phase 2: Dispatch (Outside Transaction)

The relay iterates over the claimed events and calls `await asyncio.wait_for(defer_async(**event.payload), timeout=2.0)`. Exceptions are caught per event to determine the next state.

### Phase 3: Finalize (Short Transaction with Ownership Guard)

```sql
BEGIN;
-- For successful events:
UPDATE outbox_events 
SET status = 'PROCESSED', processed_at = NOW(), claim_token = NULL
WHERE id IN (...) AND status = 'CLAIMED' AND claim_token = :generated_uuid;

-- For transient errors:
UPDATE outbox_events 
SET status = 'PENDING', next_attempt_at = NOW() + <backoff>, last_error = '...', claim_token = NULL
WHERE id IN (...) AND status = 'CLAIMED' AND claim_token = :generated_uuid;
COMMIT;
```

*Note: If `rows_affected == 0`, the relay has lost the lease (stale worker). The worker must discard the result and log a warning, but must not silently treat it as a success.*

### Phase 4: Lease Recovery (Periodic)

```sql
UPDATE outbox_events 
SET status = 'PENDING', claim_token = NULL
WHERE status = 'CLAIMED' AND claimed_at < NOW() - INTERVAL '3 minutes';
```

## 5. Relay Architecture (Standalone Process)

The Outbox Relay will execute as a dedicated Python process, completely isolated from the FastAPI application lifecycle.

**Execution Command:** `python -m src.infrastructure.workers.outbox_relay`

**Lifecycle:**

- **Startup:** Establishes `asyncpg` pool.
- **Polling Loop:** Queries for `PENDING` events. If 0 records are found, `await asyncio.sleep(POLL_INTERVAL)` (e.g., 2 seconds).
- **Graceful Shutdown:** Intercepts `SIGTERM` and `SIGINT`. Sets a shutdown `asyncio.Event`. The loop finishes the current batch (up to Phase 3) and exits cleanly.
- **Resilience:** If PostgreSQL is unreachable, the relay catches `OperationalError`, logs the failure, and sleeps with an exponential backoff before retrying.

## 6. Serialization Boundary (Payload Contract)

The `payload` JSONB column must contain **only stable primitive identifiers**. It acts as a routing slip, not a domain snapshot.

**Allowed Payload:**

```json
{
  "content_version_id": "550e8400-e29b-41d4-a716-446655440000",
  "platform": "linkedin"
}
```

**Prohibited Payload:**
Serializing full representations of the Article, EditorialBrief, or ContentVersion is forbidden. The worker must use the IDs to fetch the latest canonical state from the database. This prevents schema mismatch crashes and guarantees the worker operates on fresh data.

## 7. Migration Strategy

The `outbox_events` table is part of the application infrastructure. It will be managed via standard Alembic migrations alongside the domain tables. This does not violate IC-006, which strictly isolates Procrastinate's internal schema (`procrastinate_jobs`, etc.) from Alembic.

## 8. Objective Acceptance Criteria

1. **Relay Isolation:** Relay runs in a dedicated terminal/process and responds to SIGTERM cleanly.
2. **Lock Avoidance:** `defer_async()` is proven to execute outside the `SELECT FOR UPDATE` transaction.
3. **Lease Guard:** Setting an event to `CLAIMED` and providing a wrong `claim_token` during Finalize results in `rows_affected=0` and does not alter the record.
4. **Resilience Proof:** Shutting down Procrastinate's database connection during dispatch results in the outbox event receiving an incremented `attempt_count` and returning to `PENDING`.
5. **No Domain Leakage:** The application layer uses a clean Repository interface (`OutboxRepository.append_event`) and has no imports from Procrastinate.
