# RECONCILIATION REVIEW (Step 5)

**Status:** Completed

This document reconciles the findings from the `DATABASE-ARCHITECT-REVIEW.md`, `SENIOR-ARCHITECT-REVIEW.md`, and `RED-TEAM-REVIEW.md` to produce the final `DATABASE-SPECIFICATION.md`.

## 1. Missing Entities (Senior Architect Finding 1)
- **Resolution**: ACCEPTED. `validation_results` and `approval_decisions` will be formalized as separate tables with FKs to `content_versions`.

## 2. Premature Infrastructure (Senior Architect Finding 2)
- **Resolution**: ACCEPTED. The exact 7-day retention rule for `outbox_events` is removed from the DB Spec. It is marked as an "Operational Pruning Requirement" rather than a strict DB schema concern.

## 3. Duplicate Dispatch / Idempotency (Red Team Finding 3)
- **Resolution**: ACCEPTED. The Outbox pattern introduces At-Least-Once delivery. The specification will be updated to explicitly state that the worker handling the Procrastinate task MUST be idempotent (e.g., verifying `ContentVersion.status` using CAS before proceeding with the API call).

## 4. Soft-Delete + FK Orphaning (Red Team Finding 4)
- **Resolution**: ACCEPTED. A strict constraint will be added to the specification: All Repository read queries joining across `Article`, `EditorialBrief`, and `ContentVersion` MUST include `deleted_at IS NULL` on all parent entities to prevent operating on zombie records.

## 5. Immutability Violation Prevention (Red Team Finding 5)
- **Resolution**: REJECTED (At DB Level). We will not use PostgreSQL triggers to enforce immutability of `publication_attempts` or audit tables. In a Hexagonal Architecture, the Repository port is the sole owner of persistence logic. Adding triggers scatters business logic to the database layer. This invariant will be strictly enforced in the Application layer (Repository Implementation) and verified via CI/tests.

## 6. Next Actions
Apply these resolutions to the final `DATABASE-SPECIFICATION.md` and declare Decision Readiness.
