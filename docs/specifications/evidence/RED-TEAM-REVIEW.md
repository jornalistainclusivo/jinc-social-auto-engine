# RED TEAM ADVERSARIAL REVIEW (Step 4)

**Author:** Red Team
**Status:** Completed

We have attacked the theoretical bounds of the `DATABASE-SPECIFICATION.md` and the DB Architect's design. Here are the findings:

### 1. Concurrent CAS Race on State Transitions
- **Vector**: Two workers try to claim `APPROVED -> SCHEDULED` on the same `ContentVersion` simultaneously.
- **Analysis**: The CAS `UPDATE ... WHERE id = $1 AND status = 'APPROVED'` will properly lock the row. The first transaction commits, the second gets `rows_affected = 0`.
- **Finding**: SAFE. The CAS guard works at the PG MVCC level.

### 2. The "Silent Regeneration" Attack
- **Vector**: User clicks "Regenerate" twice rapidly. Does this overwrite `ContentVersion`?
- **Analysis**: The spec says "Regeneration creates a NEW `ContentVersion`". So two rapid clicks create two parallel `ContentVersions` in `GENERATED` state. 
- **Finding**: OBSERVATION. This is safe, but could lead to UI confusion if both are edited.

### 3. Outbox Duplicate Dispatch
- **Vector**: Polling worker crashes *after* reading from `outbox_events` but *before* calling `defer_async()` or updating status to `PROCESSED`.
- **Analysis**: The worker restarts, reads the same `PENDING` event, and dispatches it. The task gets enqueued twice in Procrastinate.
- **Severity**: MAJOR.
- **Reason**: The outbox pattern guarantees *At-Least-Once* delivery, not exactly-once. The Procrastinate tasks MUST be idempotent. The spec does not explicitly mandate worker idempotency for handling identical outbox payloads.

### 4. Soft-Delete + FK Orphaning
- **Vector**: An `Article` is soft-deleted. The `EditorialBrief` is left active. A user approves a `ContentVersion` tied to that brief.
- **Analysis**: The `deleted_at` column is not enforced by DB FKs (only standard constraints). If the application does not cascade soft-deletes or check parent `deleted_at`, we can operate on zombies.
- **Severity**: MINOR.
- **Reason**: Requires application-level query scopes to always check `WHERE deleted_at IS NULL` on joins.

### 5. PublicationAttempt Immutability Violation
- **Vector**: A rogue transaction deletes a `PublicationAttempt` to hide a failure.
- **Analysis**: Table lacks triggers to prevent DELETE or UPDATE of non-updatable fields.
- **Severity**: MINOR.
- **Reason**: We rely on the application port (Repository) to not issue DELETEs, per SDD Hexagonal rules, but DB-level `BEFORE DELETE` triggers would strictly enforce it.

### 6. Transaction Boundary Failure
- **Vector**: A worker writes to `PublicationAttempt`, then issues the external API call, then commits. The external API is slow and holds the PG connection hostage.
- **Analysis**: The Recovery Protocol explicitly states Phase 2 (Dispatch Initiation) commits *before* Phase 3 (External Call). 
- **Finding**: SAFE, assuming strict adherence to the protocol.

### 7. Stuck 'PUBLISHING' State
- **Vector**: Worker dies during external call. State is `PUBLISHING`. 
- **Analysis**: The recovery TTL handles this (Phase 4c). But how is the TTL enforced? The spec requires an index on `updated_at` where `status = 'PUBLISHING'`, which is present. 
- **Finding**: SAFE.
