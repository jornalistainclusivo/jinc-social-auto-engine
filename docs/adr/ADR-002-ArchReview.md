# ADR-002 Architecture Review Report

**Status:** Independent Review — Do Not Modify ADR-002-Analysis.md Based on This Report Alone  
**Artifact Reviewed:** `docs/adr/ADR-002-Analysis.md`  
**Review Date:** 2026-08-31  
**Authority:** This review is advisory. Human decision remains required.

---

## Executive Summary

The ADR-002 Analysis is a substantially well-structured persistence architecture analysis. It correctly identifies the relational nature of the domain, applies the constitutional constraints, and properly separates evidence levels. The preliminary recommendation (Option D: PostgreSQL + State Transition History) is architecturally sound for the scope described.

However, the review identifies **four significant findings** and **two missing architectural decisions** that must be resolved before the analysis is eligible for acceptance.

**Review Outcome: CONDITIONAL — Requires Resolution Before Acceptance**

---

## Findings

### FINDING-001 — Severity: High
**CAS Is Presented As Universally Sufficient, But Its Atomicity Assumption Requires Verification**

**Location:** §8 (Concurrency Analysis), §7 (Transaction Boundary Analysis), §19 (Recommendation)

**Observation:**
The analysis consistently relies on conditional UPDATE (`UPDATE ... WHERE status = 'X'`) as the primary concurrency safety mechanism. This is stated as atomic at the database level, which is correct *for single-table row updates in a single statement*.

**Critical gap:** The analysis does not address whether multi-table operations that *should be atomic* are correctly scoped into a single explicit database transaction. For example:
- **Approve Content** requires both: (a) CAS on `content_versions` AND (b) INSERT into `state_transitions`. These must be in the same transaction.
- **Record Publication Attempt** requires INSERT + UPDATE as a unit.

If the application issues the CAS UPDATE and then the INSERT to `state_transitions` in two separate database calls *without an explicit transaction*, a crash between them leaves the system in an inconsistent state: the state changed but the audit record was never written.

**The analysis asserts** (§11): "A single append-only table, inserted within the same transaction as the state change." — but never formally analyzes how *the application layer enforces this guarantee*. Does the Repository pattern guarantee co-transactionality? Is the Unit of Work pattern required?

**Finding:** The CAS mechanism protects single-row state transitions. It does not automatically protect multi-table atomic operations. The analysis must explicitly address whether the persistence layer enforces transaction demarcation at the Use Case boundary, and how.

---

### FINDING-002 — Severity: High
**The "Effectively Once" Guarantee Has An Unaddressed Race Condition**

**Location:** §4.E, §8 Scenario 4, §9 Class 2, §10

**Observation:**
The "effectively once" publication strategy relies on:
1. CAS `APPROVED → SCHEDULED` as an exclusive claim.
2. External API call.
3. Record result including `external_publication_id`.
4. On crash-recovery retry: check for existing `external_publication_id` before dispatching again.

**The race condition not analyzed:**

Consider a process crash that occurs *between steps 2 and 3*. The content was published externally but the `external_publication_id` was never stored. On recovery, the worker finds `status = SCHEDULED` and no `external_publication_id`. According to the described strategy, it proceeds with a new publication attempt.

The analysis acknowledges this residual risk as "Low-to-moderate" but does not analyze what determines whether the guard query (checking for `external_publication_id`) is actually executed *before* the retry dispatch. In particular:

- Who issues the "check for stuck SCHEDULED records" recovery query?
- Is that check itself idempotent and crash-safe?
- What is the exact recovery window—does the worker query BEFORE creating a new `PublicationAttempt`, or AFTER?

The `external_publication_id` guard is stated as the mitigation, but the *protocol for the guard being consulted* is not defined. Without a defined protocol, the guard provides no architectural guarantee—it provides only a guideline for implementation.

**Finding:** The "effectively once" claim requires a formally defined recovery protocol. The analysis must specify the exact sequence: (a) Query existing attempts for a `SCHEDULED` content version; (b) if any has a non-null `external_publication_id`, mark as PUBLISHED and abort retry; (c) only then dispatch a new attempt. This must be framed as an explicit application-layer invariant, not an implementation suggestion.

---

### FINDING-003 — Severity: Medium
**The `state_transitions` Table Has An Underspecified Enforcement Boundary**

**Location:** §6 Option D, §11 Auditability Analysis, §17 Risks

**Observation:**
Option D's distinguishing feature is the `state_transitions` table. The analysis correctly identifies it as the audit mechanism and lists it as a risk that data may not be written ("Audit table neglect"). The proposed mitigation is: "must be written within the same transaction as the state change."

However:

1. **The `entity_id` column is defined as `UUID FK`**, but the table uses `entity_type TEXT` as a discriminator. This is a polymorphic foreign key — a known PostgreSQL anti-pattern for referential integrity because `entity_id` cannot have a real FK to multiple tables simultaneously. If the analysis proceeds to schema design, this will surface as a contradiction.

2. **The `actor_id` field is `TEXT`**, but §14 of the SDD states the authentication boundary is `[PROPOSED - UNDECIDED]`. If there is no human identity system yet defined, how is `actor_id` populated for system-automated transitions (e.g., `GENERATED → VALIDATED` which requires no human)? The analysis does not differentiate between human-initiated transitions (which have a real `actor_id`) and system-initiated transitions (which do not).

**Finding:** The `state_transitions` schema concept contains two unresolved design tensions: (a) a polymorphic FK pattern that complicates referential integrity, and (b) an undefined `actor_id` source for system-automated transitions. The analysis should acknowledge these as open items rather than presenting the schema as resolved.

---

### FINDING-004 — Severity: Medium
**Option C (Event Sourcing) Was Rejected But Not Fully Stress-Tested Against The Stated Requirements**

**Location:** §6 Option C, §15 Counterfactual C

**Observation:**
The rejection of Event Sourcing is directionally correct and appropriately labeled as `ARCHITECTURAL JUDGMENT`. However, the analysis makes the claim: "Zero additional benefit over the Hybrid approach for the current PRD requirements."

This claim is too strong and is **not supported** by the evidence presented:

- Event Sourcing provides **native recovery semantics**: if the event store records `PublicationAttemptDispatched` *before* the external call, replay is straightforward.
- Event Sourcing's audit trail is **structurally enforced by the architecture** rather than by application-discipline. The risk identified in FINDING-003 (audit table neglect) does not exist in a properly implemented event-sourced system.

The claim "zero additional benefit" is an `OPINION`, not an `ARCHITECTURAL JUDGMENT` supported by analysis. It should be revised to: "The additional benefits of Event Sourcing (automated auditability, native recovery) do not justify its implementation and operational complexity for an MVP team." This is a defensible architectural judgment; "zero benefit" is not.

**Finding:** Revise the Event Sourcing rejection rationale to accurately represent its benefits while maintaining the recommendation against it for the MVP. This strengthens the analysis against Red Team falsification rather than weakening it.

---

## Missing Decisions

### MISSING-001 — Undecided Aggregate Boundary

**Location:** §4.C, §12 (Repository Abstraction)

The analysis recommends "concrete port interfaces (`ArticleRepository`, `ContentVersionRepository`) per aggregate." However, the aggregate boundaries are never formally defined. Specifically:

- Is `ContentVersion` an independent aggregate, or is it part of the `Article` aggregate?
- Is `PublicationAttempt` part of `ContentVersion`, or a separate aggregate?

This matters architecturally because:
- If `ContentVersion` is within the `Article` aggregate, all operations on versions must go through the `Article` aggregate root (DDD pattern), which constrains the repository design.
- If `ContentVersion` is a separate aggregate, cross-aggregate transactions become application-layer responsibilities rather than domain-layer invariants.

The ADR should either define the aggregate boundaries or explicitly defer this to a Domain Specification document, noting the dependency.

### MISSING-002 — Schema Evolution Strategy Not Addressed

**Location:** §13 (Decision Drivers: Migration Support), §17 (Risks)

The analysis lists Migration Support as a Medium-weight driver and lists Alembic as the tool. It does not address:

- **LLM output schema evolution:** If the JSON schema of LLM-generated `ContentVersion` data changes (new fields, renamed fields), how are existing rows migrated? JSONB columns can be schema-less, but the Pydantic validation layer at the boundary will break on stale data.
- **`state_transitions` immutability during evolution:** If a state name is renamed (`FAILED_VALIDATION` → `VALIDATION_FAILED`), historical records with the old state name become inconsistent with new code.

These are not blocking for the ADR decision itself, but they are missing acknowledgments that the chosen strategy requires specific implementation discipline. Leaving them silent would create a Red Team target.

---

## Overengineering Risks

### OVER-001 — Repository Pattern Specification Risk

The analysis calls for "concrete port interfaces per aggregate" with "only the methods actually needed by use cases." This is correct in principle. However, repository patterns in Python frequently evolve from pragmatic interfaces into complex hierarchies under maintenance pressure.

**Risk:** Without an explicit rule that repository ports must be defined *interface-first from use cases downward* (not from the DB schema upward), the pattern may reverse: ORM models get created first, then methods are added as convenience, then the domain starts to depend on persistence-layer idioms.

**Recommendation:** The ADR should explicitly prohibit schema-first repository design and state that every repository method must map to a named use case method invocation.

### OVER-002 — Premature Partition of `state_transitions` Scope

The analysis proposes the `state_transitions` table captures events for both `content_versions` and `publication_attempts`. This makes the table a cross-entity audit table from day one. 

If the two entity types have fundamentally different audit query patterns (e.g., content versions are queried by editorial team, publication attempts by operational team), a single polymorphic table adds join complexity and potentially index contention as volume grows.

**Risk is low for MVP**, but the analysis does not acknowledge the trade-off.

**Recommendation:** Note explicitly that the polymorphic `state_transitions` table is acceptable for MVP volume and can be split by entity type in a future migration if query patterns diverge.

---

## Contradictions With Authoritative Documents

### CONTRA-001 — SDD §14 Authentication Boundary Conflict

**SDD §14 states:** "The decision specific about the provider (if usará OAuth, JWT próprio ou integração de sessão nativa via WordPress Authentication) is left open."

**ADR-002-Analysis §5 states (Invariant 2):** "Every `ApprovalDecision` must record `actor_id`, `timestamp`, `from_state`, `to_state`."

**Tension:** The analysis mandates recording `actor_id` without an accepted identity strategy. The analysis is correct that *something* must be recorded, but the form of `actor_id` (UUID from the JINC internal identity system? WordPress user ID? JWT sub claim?) is undecided. If the identity strategy changes, `actor_id` storage format changes, potentially requiring a migration.

**Verdict:** Not a blocking contradiction. The ADR should explicitly note that the `actor_id` is a logical identifier whose concrete format is a dependency on the Authentication ADR (a future ADR). This should be listed as an open question that does not block the persistence decision but does affect the schema detail.

---

## Acceptance Recommendation

| Area | Status | Action Required |
| :--- | :---: | :--- |
| Overall persistence direction (PostgreSQL + Hybrid) | ✅ Approved | None |
| Transaction boundary analysis | ⚠️ Conditional | Clarify multi-table transaction demarcation (FINDING-001) |
| "Effectively once" semantics | ⚠️ Conditional | Define recovery protocol formally (FINDING-002) |
| State transitions schema | ⚠️ Conditional | Acknowledge polymorphic FK limitation + system actor_id gap (FINDING-003) |
| Event Sourcing rejection | ⚠️ Conditional | Revise "zero benefit" claim (FINDING-004) |
| Aggregate boundary definition | ⚠️ Deferred | Define in Domain Specification or add as Open Question |
| Schema evolution strategy | ⚠️ Deferred | Add as explicit open question / risk |
| Authentication actor_id dependency | ℹ️ Open Question | Add as open question; does not block persistence decision |

**Overall Verdict:** `CONDITIONAL ACCEPTANCE — Proceed to Red Team with these findings visible. Revise Analysis before final acceptance.`

The preliminary recommendation (Option D: PostgreSQL + State Transition History Table) is architecturally sound and the analysis is above average quality. The identified findings are primarily gaps in precision and protocol specification, not fundamental architectural errors.

The Red Team must be instructed to specifically target FINDING-001 (multi-table atomicity) and FINDING-002 ("effectively once" protocol gap), as these are the claims most susceptible to adversarial falsification.
