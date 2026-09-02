# Phase 1A — Database Implementation Plan

**Status**: Ready for Review
**Objective**: Transform `DATABASE-SPECIFICATION.md` into SQLAlchemy models and Alembic migrations without violating Hexagonal Architecture constraints or ADR invariants.

## 1. Package / Module Structure

In adherence to Hexagonal Architecture (SDD §10) and ADR-002, the database persistence logic lives strictly in the **Infrastructure** layer.

```text
src/jinc_social_engine/
├── domain/                  # PURE: No SQLAlchemy imports. Domain entities.
├── application/             # PURE: Use cases and orchestrators.
├── ports/
│   └── repositories.py      # INTERFACES: Protocols for persistence.
└── infrastructure/
    └── database/
        ├── core/            # Engine, sessionmaker, asyncpg setup.
        │   ├── connection.py
        │   └── session.py
        ├── models/          # SQLAlchemy Declarative Models
        │   ├── base.py      # SQLAlchemy declarative base, timestamp mixin
        │   ├── article.py
        │   ├── brief.py
        │   ├── version.py
        │   ├── validation.py
        │   ├── approval.py
        │   ├── audit.py     # Per-aggregate audit tables
        │   ├── attempt.py   # Publication attempts
        │   └── outbox.py    # Outbox events
        ├── repositories/    # SQLAlchemy implementation of domain ports
        └── alembic/         # Migration environment and revisions
            ├── env.py
            ├── script.py.mako
            └── versions/
```

## 2. SQLAlchemy Mapping Strategy

- **Declarative Mapping**: Use SQLAlchemy 2.0+ Declarative Mapping (`Mapped` and `mapped_column`) with strict typing.
- **UUID Strategy**: Use `uuid.UUID` typed columns with `server_default=text("gen_random_uuid()")` to generate UUIDv4 at the PG level.
- **Timestamps**: All timestamps use timezone-aware `TIMESTAMPTZ` (SQLAlchemy `DateTime(timezone=True)`). Include a `TimestampMixin` for `created_at` and `updated_at`.
- **Enums**: Native PostgreSQL `ENUM` types for states (`ContentVersionStatus`, `OutboxStatus`), mapped via Python `enum.Enum`.
- **JSONB**: Use `sqlalchemy.dialects.postgresql.JSONB` for schema-less data (like `payload` in outbox, `metadata` in audit).
- **Foreign Keys**: Defined explicitly with strict `ON DELETE RESTRICT` to prevent accidental cascading hard deletes (violates audit constraints).
- **Soft-Delete**: Represented by a `deleted_at: Mapped[datetime | None]` column. Repositories will globally apply `.where(Model.deleted_at.is_(None))` on reads.
- **Concurrency (CAS)**: Implemented in the Repository layer using `UPDATE ... WHERE id = :id AND status = :expected_status`, strictly checking `cursor.rowcount == 1`.

## 3. Entity Mapping

### Article
- **Table**: `articles`
- **PK**: `id` (UUID)
- **Columns**: `source_id` (String), `wp_post_id` (BigInteger), `url` (String), `hash` (String), `published_at` (TIMESTAMPTZ), `created_at` (TIMESTAMPTZ), `updated_at` (TIMESTAMPTZ), `deleted_at` (TIMESTAMPTZ, Nullable).
- **Constraints/Indexes**: 
  - `UniqueConstraint('source_id', 'wp_post_id', postgresql_where=text("deleted_at IS NULL"))`.
- **Lifecycle**: Mutable. Soft-deleted.

### EditorialBrief
- **Table**: `editorial_briefs`
- **PK**: `id` (UUID)
- **FK**: `article_id` -> `articles.id`
- **Columns**: `brief_data` (JSONB), `created_at`, `updated_at`, `deleted_at`.
- **Lifecycle**: Immutable analysis result. Soft-deleted.

### ContentVersion
- **Table**: `content_versions`
- **PK**: `id` (UUID)
- **FK**: `brief_id` -> `editorial_briefs.id`
- **Columns**: `platform` (String), `content` (String), `status` (Enum), `created_at`, `updated_at`, `deleted_at`.
- **Constraints**: 
  - Explicit CheckConstraint validating `status` against valid enum strings.
- **Indexes**: 
  - Partial index on `updated_at` WHERE `status = 'PUBLISHING'` (for TTL recovery).
  - Index on `status` for fast polling.
- **Lifecycle**: State machine driven. Updates strictly via CAS.

### ValidationResult
- **Table**: `validation_results`
- **PK**: `id` (UUID)
- **FK**: `content_version_id` -> `content_versions.id`
- **Columns**: `is_valid` (Boolean), `errors` (JSONB), `created_at`.
- **Lifecycle**: Immutable append-only.

### ApprovalDecision
- **Table**: `approval_decisions`
- **PK**: `id` (UUID)
- **FK**: `content_version_id` -> `content_versions.id`
- **Columns**: `decision_type` (Enum: APPROVED, REJECTED), `actor_id` (String), `edits_made` (JSONB, Nullable), `created_at`.
- **Lifecycle**: Immutable append-only.

## 4. Audit Mapping

- **Table**: `content_version_transitions` (Per-aggregate audit table)
- **PK**: `id` (UUID)
- **FK**: `entity_id` -> `content_versions.id` (REAL foreign key ensuring integrity).
- **Columns**: 
  - `from_state` (String)
  - `to_state` (String)
  - `actor_id` (String, Nullable)
  - `actor_type` (Enum: HUMAN, SYSTEM, WORKER)
  - `reason` (String)
  - `metadata` (JSONB, Nullable)
  - `timestamp` (TIMESTAMPTZ, default `now()`)
- **Semantics**: Append-only. No `updated_at` or `deleted_at` columns. No DB-level triggers (enforced purely by the Repository Port). 
- **Integrity**: Because `ContentVersion` is soft-deleted, the FK to `content_versions.id` will never orphan the audit logs.

## 5. PublicationAttempt

- **Table**: `publication_attempts`
- **PK**: `id` (UUID)
- **FK**: `content_version_id` -> `content_versions.id`
- **Columns**: 
  - `worker_id` (String)
  - `status` (Enum: PENDING, SUCCESS, FAILED)
  - `external_publication_id` (String, Nullable)
  - `failure_reason` (String, Nullable)
  - `created_at`, `updated_at`.
- **Lifecycle**: Append-only domain semantics. Status can be updated, but external identifiers and reasons are recorded immutably. A retry creates a new record.

## 6. Outbox Mapping

- **Table**: `outbox_events`
- **PK**: `id` (UUID)
- **Columns**:
  - `aggregate_type` (String)
  - `aggregate_id` (UUID)
  - `event_type` (String)
  - `payload` (JSONB)
  - `status` (Enum: PENDING, PROCESSED)
  - `created_at` (TIMESTAMPTZ)
  - `processed_at` (TIMESTAMPTZ, Nullable)
- **Indexes**: Partial index on `status` WHERE `status = 'PENDING'` for fast relay polling.

## 7. Alembic Configuration

- **Directory**: `src/jinc_social_engine/infrastructure/database/alembic`
- **env.py**: Configured to load `asyncpg` driver natively via the application's core `engine`. It imports `Base.metadata` to support `--autogenerate`.
- **Migrations**: Sequential versions. CI must validate that `alembic check` passes (ensuring models match database schema).
- **Downgrade Policy**: Downgrade scripts will be generated alongside upgrade scripts, but CI focuses heavily on forward migrations.

## 8. Testing Strategy

### Unit Tests
- Domain entity constraints (validating state machine in Python without DB).

### Integration Tests
- Validating the Repository Port implementations in isolation using mocked database sessions to verify CAS behavior.

### Database Integration Tests (Pytest + Local PostgreSQL)
- **Schema Creation**: Verify `alembic upgrade head` works cleanly on a fresh database and `alembic downgrade base` executes without leaving artifacts.
- **CAS Behavior**: Simulate two concurrent repository `.transition_state()` calls and assert one properly yields.
- **Soft-Delete**: Assert that a soft-deleted `Article` does not appear in standard `.get()` queries but its audit logs remain accessible.
- **Audit Integrity**: Verify that a state transition inserts BOTH the updated entity and the audit record atomically.
- **Constraint Testing**: Verify that unique constraints (`source_id`, `wp_post_id`) correctly raise `IntegrityError` on duplicates.

## 9. Architecture Boundaries (Mandatory)

```python
# FORBIDDEN in Domain/Application layer:
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession
import alembic
import asyncpg
```

The domain will interact solely through Ports (Protocols/ABCs) defining abstract methods like `async def save(self, article: Article) -> None: ...`

---
*Implementation will commence upon approval of this plan.*
