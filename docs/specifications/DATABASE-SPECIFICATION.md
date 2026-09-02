# DATABASE-SPECIFICATION

**Status**: Normative (Ready for Implementation)
**Scope**: Transactional Database for JincSAE
**Primary Store**: PostgreSQL (per ADR-002)

## 1. Persistence Requirements
- **Technology**: PostgreSQL (Hybrid Audit model).
- **Architecture**: Hexagonal Architecture. The domain layer has zero knowledge of PostgreSQL or ORM.
- **Transactional Integrity**: All multi-entity workflows require atomic, durable state changes.
- **Auditability**: Mandatory per-aggregate append-only audit history tables.
- **Queueing**: Transactional Outbox Pattern to push jobs to Procrastinate, avoiding the "Lost Dispatch" failure mode (ADR-003).

## 2. Persisted Entities

### 2.1 Core Domain Entities
- **`Article`**: The canonical factual source.
- **`EditorialBrief`**: Structured analysis outcome.
- **`ContentVersion`**: Platform-specific generated content.
- **`ValidationResult`**: Proofs that accessibility/formatting rules are met.
- **`ApprovalDecision`**: Explicit record of human intervention and edits.
- **`PublicationAttempt`**: Immutable operational record of a dispatch attempt.

### 2.2 Operational / Infrastructure Entities
- **`OutboxEvent`**: Records domain events to be forwarded to the background queue (Procrastinate).
- **Per-Aggregate Audit Tables**: e.g., `content_version_transitions`.

## 3. Relationships

- `EditorialBrief` → `Article` (N:1).
- `ContentVersion` → `EditorialBrief` (N:1).
- `ValidationResult` → `ContentVersion` (1:1).
- `ApprovalDecision` → `ContentVersion` (1:1 or N:1).
- `PublicationAttempt` → `ContentVersion` (N:1).
- `content_version_transitions` → `ContentVersion` (N:1).

*Invariant:* Every `ContentVersion` must trace through a relational FK chain to its originating `Article`: `ContentVersion → EditorialBrief → Article`. (ADR-002 Invariant 3).

## 4. States & Lifecycle

### 4.1 ContentVersion State Machine
Must follow the constitutionally mandated state machine:
```
GENERATED → VALIDATED → PENDING_REVIEW → [REJECTED | APPROVED]
APPROVED → SCHEDULED → PUBLISHING → [PUBLISH_FAILED | PUBLISHED]
```
*Note: Regeneration creates a NEW `ContentVersion`, it does not rollback state. (ADR-002 Invariant 4).*

## 5. Integrity Requirements

- **Atomic State Transition Unit**: Every domain state transition requires (1) a CAS conditional UPDATE on the current-state table + (2) an INSERT into the audit history table for the aggregate, within a SINGLE explicit database transaction. (ADR-002 Invariant 1).
- **Append-Only Audit**: Audit records are immutable once created. Entities must use soft-delete (`deleted_at TIMESTAMPTZ`) to prevent audit record orphaning. (ADR-002 Invariant 2).
- **Immutable Operational Records**: `PublicationAttempt` records are append-only (only `status`, `external_publication_id`, `failure_reason` may be updated). Enforcement belongs to the Repository port implementation. (ADR-002 Invariant 5).
- **Soft-Delete Cascade**: All Repository read queries joining across domain entities MUST enforce `deleted_at IS NULL` on all parent entities to prevent operating on zombie records.

## 6. Audit Requirements

- Dedicated append-only audit tables per aggregate with REAL foreign key constraints (no polymorphic FKs).
- **Audit Record Schema**: `id`, `entity_id`, `from_state`, `to_state`, `actor_id` (TEXT), `actor_type` (HUMAN, SYSTEM, WORKER), `timestamp`, `reason`, `metadata`.

## 7. Concurrency Requirements

- **Article Ingestion Deduplication**: Unique database constraint on `(source_id, wp_post_id)` where `deleted_at IS NULL`.
- **Concurrent State Transitions**: CAS conditional UPDATE (`UPDATE ... SET status = 'TARGET', updated_at = NOW() WHERE id = $1 AND status = 'CURRENT'`). Bypassing the CAS guard is prohibited. (ADR-002 Invariant 6).
- **Scheduler & Dispatch Claim**: Exclusive claims via CAS for transitions `APPROVED → SCHEDULED` and `SCHEDULED → PUBLISHING`.

## 8. Transactional Outbox Requirements

- **Atomicity**: Domain transitions and outbox events must be inserted via the same SQLAlchemy `AsyncSession` (sharing the `asyncpg` connection/transaction).
- **Relay**: A secondary worker will poll the outbox table and issue `defer_async()` to Procrastinate.
- **Idempotency Guarantee**: Because the Outbox pattern offers at-least-once delivery, workers handling the resulting tasks MUST be idempotent. They must use CAS to verify the entity is still in the expected state before proceeding.

## 9. Retention and Lifecycle

- **Soft Delete**: `deleted_at TIMESTAMPTZ` for domain entities.
- **Publication Recovery TTL**: A `PUBLISHING` state stuck beyond a defined operational TTL triggers the crash recovery protocol.
- **Outbox Event Retention**: Operational pruning is required to remove processed events (e.g., hard-delete after 7 days).

## 10. Access Patterns & Indices

- **Primary Lookups**: by `id` (PK).
- **Unique Constraint**: `Article` table by `(source_id, wp_post_id)` WHERE `deleted_at IS NULL`.
- **State Queries**: Indices needed on `status`.
- **Outbox Polling**: `CREATE INDEX idx_outbox_events_status ON outbox_events(status) WHERE status = 'PENDING';`
- **TTL Recovery**: `CREATE INDEX idx_content_versions_publishing ON content_versions(updated_at) WHERE status = 'PUBLISHING';`
