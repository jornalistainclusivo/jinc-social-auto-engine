# ADR-003: Async Processing, Background Jobs & Workflow Execution

## Status

**Accepted**

## Context

The JincSAE (`jinc-social-engine`) editorial pipeline is inherently asynchronous, requiring long-running LLM generation calls, I/O-bound external social media platform API interactions, and future-dated execution for content scheduling.

The central architectural constraint is the **Atomic State-to-Audit-to-Event (ASAE)** invariant inherited from ADR-002 (Persistence Strategy). It strictly forbids the "Lost Dispatch" (Scenario S3) failure mode: a domain state transition must not be committed to the database without its corresponding async job being durably registered.

An extensive analysis evaluated Procrastinate, TaskIQ, ARQ, Celery, and Temporal. Procrastinate (PostgreSQL-Native Queue) was initially recommended for its theoretical capability to achieve "Direct Transactional Dispatch" by executing its job enqueue within the same PostgreSQL transaction as the domain state change.

However, mandatory Gate 1 validation empirically proved that "Direct Transactional Dispatch" is structurally impossible in the JincSAE stack. SQLAlchemy 2.0 (`asyncpg`) and Procrastinate (`psycopg3`) utilize fundamentally different database drivers, making them unable to share the same underlying TCP connection or transaction boundary. Attempting to enqueue jobs synchronously during the domain transaction resulted in jobs surviving SQLAlchemy rollbacks (the dual-write problem).

To preserve the ASAE invariant without introducing unacceptable maintenance overhead for a custom Procrastinate connector, the architecture must transition to the **Transactional Outbox Pattern**.

## Decision

**Procrastinate (PostgreSQL-Native Queue) is selected as the asynchronous job engine, with the strict mandate to implement the Transactional Outbox Pattern.**

## Rationale

The decision to adopt Procrastinate via the Outbox Pattern is based on:

1. **Operational Simplicity:** Procrastinate utilizes the already-mandated PostgreSQL database (ADR-002), requiring zero additional infrastructure services (e.g., Redis, RabbitMQ) to monitor, secure, or scale.
2. **ASAE Invariant Compliance:** Domain transitions and outbox events will both be inserted via the SQLAlchemy `AsyncSession` (sharing the exact same `asyncpg` connection and transaction). A secondary relay/publisher worker will poll the outbox table and issue the `defer_async()` calls to Procrastinate, completely eliminating the Lost Dispatch risk.
3. **Python/asyncio Compatibility:** Procrastinate natively supports modern Python `async/await` flows, aligning perfectly with the ADR-001 runtime decision.
4. **Native Durability:** Scheduled and delayed execution is fully durable in PostgreSQL, whereas alternatives like Redis require specific, non-default configurations (e.g., `appendfsync always`) to achieve similar durability.

### Rejected Options

- **TaskIQ / ARQ:** Both are native asyncio queue solutions that would require adding Redis to the infrastructure stack. Since the Transactional Outbox Pattern requires a database table anyway, routing through a separate Redis cluster adds operational overhead and point-of-failure without structural benefit.
- **Celery:** Cannot participate in PostgreSQL transactions natively, uses a synchronous worker model by default, and introduces infrastructure dependencies disproportionate to the MVP workload.
- **Temporal:** While powerful, its deployment footprint (multiple infrastructure services) and programming model complexity are disproportionate to the currently scoped JincSAE pipeline.

## Consequences

### Positive

- **Zero Infrastructure Sprawl:** Keeps the architecture strictly limited to the Web/App containers and PostgreSQL.
- **Bulletproof Atomicity:** The Transactional Outbox completely solves the Lost Dispatch scenario. Domain state and the intent to dispatch an event commit or roll back perfectly together.

### Negative / Trade-offs

- **Custom Outbox Relay Required:** The engineering team must build, test, and maintain a secondary relay worker whose sole responsibility is polling the outbox table and publishing jobs to Procrastinate.
- **Coupled Availability:** A PostgreSQL outage results in both an application and queue outage.
- **Zombie Worker Risk (Implementation Constraint):** Because asyncio single-threads the worker event loop, all network I/O operations within task functions *must* use async-compatible libraries (e.g., `httpx` instead of `requests`) to prevent heartbeat suspension and false lease expiry.
- **Database Load:** High queue volume will place additional write and VACUUM pressure on the primary PostgreSQL database, necessitating strict operational policies for pruning succeeded and failed jobs.

## Related Documents

- `docs/ENGINEERING_CONSTITUTION.md`
- `docs/SDD.md` (Software Design Document v1.1.0)
- `docs/adr/ADR-001-Runtime-Language.md` (Runtime Language)
- `docs/adr/ADR-002-Persistence-Strategy.md` (Persistence Strategy)
- `docs/adr/ADR-003-Reconciliation.md` (Reconciliation / Final Decision Brief)
- `docs/adr/evidence/ADR-003-Gate-1-Transactional-Enqueue.md` (Empirical evidence rejecting Direct Transactional Dispatch)
