# DATABASE ARCHITECT REVIEW (Step 2)

**Author:** Database Architect
**Status:** Completed

## 1. Relational Integrity & Schema Design

### Entities & Foreign Keys
- **`articles`**: `id` (UUID, PK), `source_id` (TEXT), `wp_post_id` (BIGINT), `url` (TEXT), `hash` (TEXT), `published_at` (TIMESTAMPTZ), `created_at` (TIMESTAMPTZ), `deleted_at` (TIMESTAMPTZ).
  *Justification*: Soft delete preserves FK integrity for audits. `(source_id, wp_post_id)` must have a `UNIQUE` constraint to prevent duplicate ingestion.
- **`editorial_briefs`**: `id` (UUID, PK), `article_id` (UUID, FK -> `articles.id`), `brief_data` (JSONB), `created_at` (TIMESTAMPTZ), `deleted_at` (TIMESTAMPTZ).
- **`content_versions`**: `id` (UUID, PK), `brief_id` (UUID, FK -> `editorial_briefs.id`), `platform` (VARCHAR), `content` (TEXT), `status` (VARCHAR), `created_at`, `updated_at`, `deleted_at`.
  *Justification*: `updated_at` is required for TTL recovery queries on the `PUBLISHING` state.
- **`publication_attempts`**: `id` (UUID, PK), `content_version_id` (UUID, FK -> `content_versions.id`), `worker_id` (TEXT), `status` (VARCHAR), `external_publication_id` (TEXT), `failure_reason` (TEXT), `created_at`, `updated_at`.
  *Justification*: Immutable domain record (append-only updates for status).
- **`outbox_events`**: `id` (UUID, PK), `aggregate_type` (VARCHAR), `aggregate_id` (UUID), `event_type` (VARCHAR), `payload` (JSONB), `status` (VARCHAR) [PENDING, PROCESSED], `created_at`, `processed_at`.
  *Justification*: Transactional Outbox pattern requires an explicit outbox table.

## 2. Integrity & Constraints
- **Nullability**: All timestamps except `deleted_at` and `updated_at` (where applicable) must be `NOT NULL`. `external_publication_id` in `publication_attempts` is `NULL` initially.
- **Check Constraints**: `status` column in `content_versions` should preferably have a `CHECK (status IN ('GENERATED', 'VALIDATED', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'SCHEDULED', 'PUBLISHING', 'PUBLISH_FAILED', 'PUBLISHED'))` to prevent invalid states at the database level.

## 3. Concurrency Control (CAS)
- The CAS conditional update is implemented purely via SQL `UPDATE ... WHERE id = $1 AND status = $2`.
- Since we require `updated_at` for TTL recovery, the CAS query should also update `updated_at = NOW()`.

## 4. Audit Implementation
- **`content_version_transitions`**: `id` (UUID, PK), `content_version_id` (UUID, FK), `from_state` (VARCHAR), `to_state` (VARCHAR), `actor_id` (TEXT, NULL), `actor_type` (VARCHAR), `timestamp` (TIMESTAMPTZ).
  *Justification*: Pure append-only. FK constraint guarantees no orphaned audits.

## 5. Indexing Strategy
- **Outbox Polling**: `CREATE INDEX idx_outbox_events_status ON outbox_events(status) WHERE status = 'PENDING';` (Partial index for fast polling).
- **Recovery TTL**: `CREATE INDEX idx_content_versions_publishing ON content_versions(updated_at) WHERE status = 'PUBLISHING';` (Partial index to find stuck jobs).
- **Unique Article Ingestion**: `CREATE UNIQUE INDEX idx_articles_source_wp ON articles(source_id, wp_post_id) WHERE deleted_at IS NULL;` (Partial unique index allows re-ingestion if hard deleted, though we use soft delete).

## 6. Retention (Addressing UNDECIDED)
- **Outbox Event Retention**: The outbox table will grow unbounded. *Decision*: Events should be hard-deleted or archived 7 days after `status = 'PROCESSED'`.
- **Procrastinate Jobs**: Let Procrastinate handle its own retention via its standard maintenance functions.
