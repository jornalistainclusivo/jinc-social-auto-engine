# JincSAE Engineering Constitution

## Jornalista Inclusivo Social Automation Engine

**Status:** Active
**Version:** 1.0.0
**Authority Level:** Foundational Engineering Policy
**Applies To:** Humans, AI Agents, Automation Tools and CI/CD Systems
**Repository:** `jinc-social-engine`

---

## 1. Purpose

This document establishes the foundational engineering principles governing the development of the **Jornalista Inclusivo Social Automation Engine (JincSAE)**.

The Constitution exists to ensure that the project remains:

* architecturally coherent;
* editorially reliable;
* factually grounded;
* accessible;
* secure;
* testable;
* maintainable;
* auditable;
* resilient to uncontrolled AI-assisted development.

The JincSAE is developed in an environment where AI agents may participate in:

* analysis;
* planning;
* specification;
* implementation;
* testing;
* refactoring;
* documentation;
* code review.

Therefore, the project must not depend on:

> implicit assumptions, agent memory, conversational context, or undocumented architectural decisions.

The repository itself must contain sufficient explicit constraints to guide implementation.

---

## 2. Constitutional Authority

This Constitution has precedence over:

1. implementation convenience;
2. AI-generated suggestions;
3. temporary shortcuts;
4. undocumented assumptions;
5. agent preferences.

The governing hierarchy is:

```text
Engineering Constitution
        ↓
PRD
        ↓
Architecture / SDD
        ↓
ADRs
        ↓
Domain Specifications
        ↓
Feature Specifications
        ↓
Acceptance Criteria
        ↓
Tests
        ↓
Implementation
```

No implementation may intentionally violate a higher-level governing document.

When conflicts exist:

```text
Higher-level authority prevails.
```

---

## 3. Core Engineering Principle

The JincSAE SHALL be developed according to the principle:

> **Specifications define intended behavior. Tests verify behavior. Implementations may change.**

Therefore:

```text
Specification
      ≠
Implementation
```

The implementation is replaceable.

The behavioral contract is authoritative.

---

## 4. Principle I — Article Canonical Authority

The published source article is the primary factual authority of the system.

The system MUST treat the article as the canonical source for generated social content.

AI-generated content MUST NOT:

* invent facts;
* invent quotations;
* alter numerical data;
* fabricate sources;
* attribute statements to individuals not supported by the source;
* present inference as fact.

Every generated social artifact MUST maintain traceability to its source article.

Conceptually:

```text
Article
   │
   ▼
Editorial Analysis
   │
   ▼
Generated Content
```

The reverse relationship is mandatory:

```text
Generated Content
       │
       └──────► Source Article
```

A generated artifact without a source reference is invalid.

---

## 5. Principle II — AI Output Is Untrusted Input

Large Language Model output MUST be treated as untrusted until validated.

The system MUST NOT assume that generated content is:

* factually correct;
* structurally valid;
* safe;
* complete;
* compliant with platform rules.

The mandatory pattern is:

```text
LLM Output
    │
    ▼
Schema Validation
    │
    ▼
Editorial Validation
    │
    ▼
Accessibility Validation
    │
    ▼
Domain Validation
    │
    ▼
Trusted Application State
```

AI output MUST NOT directly mutate critical application state.

AI output MUST NOT directly trigger publication.

---

## 6. Principle III — Structured Output Over Free Text

Whenever possible, AI systems MUST produce structured output.

Preferred pattern:

```text
LLM
 ↓
Structured Schema
 ↓
Validation
 ↓
Domain Object
```

Discouraged pattern:

```text
LLM
 ↓
Unstructured Text
 ↓
Application Logic
```

Structured outputs SHOULD use explicit schemas.

Examples include:

* JSON Schema;
* Pydantic models;
* typed domain objects.

A model response that fails schema validation MUST be rejected, repaired through a controlled process, or regenerated.

The application MUST NOT silently reinterpret malformed AI output.

---

## 7. Principle IV — Specification Before Implementation

No non-trivial feature SHOULD begin with implementation.

The minimum workflow is:

```text
Problem
   ↓
Specification
   ↓
Acceptance Criteria
   ↓
Implementation Plan
   ↓
Tests
   ↓
Implementation
   ↓
Verification
```

AI agents MUST NOT independently expand feature scope without an explicit specification update.

The phrase:

> "Implement the feature"

is insufficient for complex architectural work.

A feature MUST have an identifiable behavioral contract.

---

## 8. Principle V — Plan Before Code

For non-trivial changes, agents MUST first produce an implementation plan.

The plan MUST identify:

* files to create;
* files to modify;
* domain concepts affected;
* dependencies;
* risks;
* tests to add or modify.

The agent SHOULD NOT begin implementation until the plan has been reviewed when the change affects:

* architecture;
* domain models;
* database schemas;
* external APIs;
* security;
* publication workflows.

Preferred workflow:

```text
SPEC
 ↓
PLAN
 ↓
REVIEW
 ↓
TEST
 ↓
IMPLEMENT
 ↓
VERIFY
```

---

## 9. Principle VI — Small, Atomic Changes

Features MUST be decomposed into small, reviewable units.

Agents SHOULD NOT implement multiple unrelated concerns in a single change.

Avoid:

```text
"Build the complete social media backend."
```

Prefer:

```text
001 — Article Ingestion
002 — Editorial Brief Generation
003 — LinkedIn Generation
004 — Content Validation
005 — Approval Workflow
```

Each feature SHOULD have:

* a defined objective;
* explicit scope;
* non-goals;
* acceptance criteria;
* implementation tasks.

---

## 10. Principle VII — Domain Before Framework

The core business domain MUST NOT depend on:

* FastAPI;
* WordPress;
* PostgreSQL;
* OpenAI;
* LinkedIn;
* Meta APIs;
* Bluesky.

The preferred dependency direction is:

```text
External Systems
        │
        ▼
Infrastructure
        │
        ▼
Application Layer
        │
        ▼
Domain Layer
```

The Domain Layer MUST NOT depend on infrastructure.

---

## 11. Principle VIII — External Systems Are Adapters

All external services MUST be isolated behind explicit interfaces or adapters.

Examples:

```text
WordPress
    │
    ▼
WordPressAdapter
```

```text
LLM Provider
    │
    ▼
EditorialAnalysisProvider
```

```text
LinkedIn API
    │
    ▼
LinkedInPublisher
```

The domain MUST NOT directly depend on vendor-specific SDKs.

Vendor changes SHOULD affect adapters rather than core business logic.

---

## 12. Principle IX — Editorial Logic Is a Domain Concern

Editorial rules MUST NOT be scattered across:

* API controllers;
* platform SDK integrations;
* HTTP handlers;
* background workers;
* prompt strings.

Editorial logic belongs to explicit domain or application services.

Examples:

```text
EditorialBrief
EditorialPolicy
ContentValidator
FactualGroundingService
AccessibilityValidator
```

Prompts MUST NOT become the only location where critical business rules exist.

If a rule is important enough to protect:

> it must exist outside the prompt.

---

## 13. Principle X — Separation of Generation and Publication

Content generation MUST be separated from publication.

```text
Generator
    ≠
Publisher
```

The following pipeline is mandatory:

```text
Generate
   ↓
Validate
   ↓
Review
   ↓
Approve
   ↓
Schedule
   ↓
Publish
```

A content generator MUST NOT directly publish content.

A publisher MUST NOT generate editorial content.

---

## 14. Principle XI — Explicit State Machines

Critical workflows MUST use explicit state transitions.

Implicit states based on:

* null values;
* timestamps;
* missing fields;
* naming conventions;

SHOULD be avoided.

The publication lifecycle MUST be explicitly represented.

Example:

```text
GENERATED
    ↓
VALIDATED
    ↓
PENDING_REVIEW
    ├──────────► REJECTED
    │
    ▼
APPROVED
    ↓
SCHEDULED
    ↓
PUBLISHING
    ↓
PUBLISHED
```

Invalid transitions MUST be rejected.

Example:

```text
GENERATED
   ↓
PUBLISHED
```

is invalid unless explicitly authorized by a future specification.

---

## 15. Principle XII — Human Authority Over Publication

The initial publication model is:

> **Human-in-the-loop**

AI systems MAY:

* analyze;
* classify;
* summarize;
* generate;
* recommend.

AI systems MUST NOT independently receive final editorial authority unless a future specification explicitly changes this policy.

Human approval is required before publication during the MVP.

---

## 16. Principle XIII — Accessibility Is a First-Class Requirement

Accessibility MUST NOT be treated as:

* optional enhancement;
* post-processing;
* cosmetic improvement.

Accessibility requirements belong to:

* specifications;
* acceptance criteria;
* validation;
* testing;
* definition of done.

Generated content SHOULD consider:

* readability;
* meaningful emoji usage;
* excessive decorative symbols;
* hashtag overload;
* accessible image descriptions;
* alternative text;
* caption requirements where applicable.

Accessibility validation MUST be extensible as platform capabilities evolve.

---

## 17. Principle XIV — Factual Traceability

The system SHOULD be able to answer:

> Where did this claim come from?

Important factual claims SHOULD maintain source provenance.

Conceptually:

```text
Generated Claim
       │
       ▼
Source Reference
       │
       ▼
Article Location
```

Where feasible, the Editorial Brief SHOULD distinguish:

* facts;
* quotations;
* interpretation;
* recommendations;
* editorial framing.

These categories MUST NOT be silently conflated.

---

## 18. Principle XV — No Silent Failure

Critical failures MUST NOT disappear silently.

The system MUST provide observable failure states.

Examples:

```text
LLM validation failed
WordPress ingestion failed
Platform publication failed
Webhook signature invalid
Approval transition invalid
```

Failures MUST produce appropriate:

* logs;
* status records;
* error states.

Silent fallback behavior SHOULD be avoided when it could compromise editorial integrity.

---

## 19. Principle XVI — Idempotency

External events MUST be assumed to be duplicated.

Webhook processing MUST be idempotent.

Example:

```text
WordPress Event
       │
       ├── First Delivery
       │
       └── Duplicate Delivery
```

The result MUST NOT be:

```text
Two Articles
Two Generation Jobs
Two Publications
```

Idempotency is mandatory for:

* webhooks;
* publication jobs;
* retries;
* external event processing.

---

## 20. Principle XVII — Explicit Error Handling

Exceptions MUST NOT be used as invisible control flow.

Expected failures SHOULD be represented explicitly.

Examples:

* validation errors;
* authentication failures;
* duplicate events;
* rate limits;
* unavailable APIs.

The system MUST distinguish between:

```text
Retryable Failure
```

and:

```text
Permanent Failure
```

---

## 21. Principle XVIII — Security by Default

Secrets MUST NOT be:

* committed to Git;
* hardcoded in source files;
* embedded in prompts;
* written to logs.

Sensitive configuration MUST be provided through approved configuration mechanisms.

Examples:

```text
Environment Variables
Secret Managers
Deployment Configuration
```

The repository SHOULD include:

```text
.env.example
```

but MUST NOT include production credentials.

---

## 22. Principle XIX — Least Privilege

External integrations SHOULD receive only the permissions required for their function.

Credentials MUST be separated by responsibility where practical.

For example:

```text
Read WordPress
```

should not automatically imply:

```text
Modify WordPress Content
```

Similarly:

```text
Generate Content
```

does not require:

```text
Publish Content
```

---

## 23. Principle XX — Test the Contract, Not the Implementation

Tests MUST primarily verify observable behavior.

Avoid tests that depend unnecessarily on:

* private methods;
* internal variable names;
* implementation details.

Preferred:

```text
Given
When
Then
```

Example:

```text
Given a duplicate webhook event
When the event is processed twice
Then only one article is created
```

The implementation may change.

The contract must remain stable.

---

## 24. Principle XXI — Test Pyramid

The project SHOULD prioritize:

```text
        E2E
       ─────
   Integration
   ───────────
       Unit
  ───────────────
```

Unit tests SHOULD cover:

* domain rules;
* state transitions;
* validation logic;
* transformation rules.

Integration tests SHOULD cover:

* databases;
* webhooks;
* external adapters;
* queues.

End-to-end tests SHOULD cover critical workflows.

---

## 25. Principle XXII — AI Evaluation Is Part of Testing

Traditional tests are insufficient for AI-generated behavior.

The project SHOULD implement evaluation criteria for:

* factual grounding;
* schema compliance;
* unsupported claims;
* platform constraints;
* accessibility requirements;
* editorial consistency.

AI evaluation SHOULD distinguish between:

```text
Deterministic Validation
```

and:

```text
Probabilistic Quality Evaluation
```

The latter MUST NOT replace deterministic safety checks.

---

## 26. Principle XXIII — Deterministic Rules Protect Critical Boundaries

Critical rules SHOULD NOT depend exclusively on probabilistic models.

Examples of deterministic rules:

* publication requires approval;
* invalid state transitions are rejected;
* duplicate webhook events are ignored;
* malformed schemas are rejected;
* missing required fields are invalid.

An LLM MUST NOT be the sole authority for these decisions.

---

## 27. Principle XXIV — Prompt Versioning

Prompts that influence production behavior MUST be versioned.

Each significant generation SHOULD be traceable to:

* prompt identifier;
* prompt version;
* model identifier;
* relevant generation configuration.

Conceptually:

```text
Generated Content
      │
      ├── Prompt Version
      ├── Model
      ├── Configuration
      └── Timestamp
```

Production prompts MUST NOT exist only inside informal agent conversations.

---

## 28. Principle XXV — Reproducibility

Where technically feasible, the system SHOULD preserve sufficient metadata to reproduce a generation.

This includes:

* source article version;
* Editorial Brief version;
* prompt version;
* model identifier;
* generation parameters.

Perfect deterministic reproduction is not always possible with generative systems.

The system MUST nevertheless preserve maximum practical traceability.

---

## 29. Principle XXVI — Version Domain Contracts

Changes to important schemas MUST be managed deliberately.

Examples:

```text
EditorialBrief v1
EditorialBrief v2
```

Breaking changes MUST NOT silently invalidate existing stored data.

Schema migrations MUST be specified and tested.

---

## 30. Principle XXVII — Database Changes Require Explicit Design

Database changes MUST NOT be introduced casually through AI-generated migrations.

Schema changes SHOULD include:

* purpose;
* affected entities;
* migration strategy;
* rollback considerations;
* data integrity implications.

Destructive migrations require explicit review.

---

## 31. Principle XXVIII — Documentation Is Part of the System

Documentation is not optional project decoration.

The repository MUST maintain documentation for:

* product requirements;
* architecture;
* major decisions;
* domain concepts;
* feature specifications;
* setup procedures.

When architecture changes, documentation MUST be reviewed.

Code and documentation SHOULD NOT silently diverge.

---

## 32. Principle XXIX — Architecture Decisions Must Be Recorded

Significant decisions MUST be captured in ADRs.

Examples include:

* choosing FastAPI;
* choosing PostgreSQL;
* selecting an LLM provider;
* webhook architecture;
* approval workflow;
* queue technology.

An ADR SHOULD answer:

```text
Context
Decision
Alternatives
Consequences
```

Agents MUST NOT silently introduce major architectural technologies.

---

## 33. Principle XXX — No Architecture by Accident

A framework, library, pattern, or infrastructure dependency MUST NOT become part of the architecture merely because:

> an AI agent generated it.

New architectural dependencies SHOULD require:

1. justification;
2. compatibility analysis;
3. explicit decision;
4. documentation.

---

## 34. Principle XXXI — Repository Is the Persistent Memory

AI agents have limited and non-authoritative conversational memory.

The repository is the project's durable knowledge base.

Important information MUST be persisted in:

* specifications;
* ADRs;
* documentation;
* schemas;
* tests.

Critical project knowledge MUST NOT exist exclusively in a chat conversation.

---

## 35. Principle XXXII — Agents Must Read Before Writing

Before modifying a component, an AI agent SHOULD inspect:

1. the Engineering Constitution;
2. relevant specifications;
3. related ADRs;
4. existing tests;
5. existing implementation.

Agents MUST NOT assume architecture without evidence.

---

## 36. Principle XXXIII — Agents Must Respect Scope

Agents MUST NOT expand a task beyond its defined scope.

If a specification requests:

```text
Article Ingestion
```

the agent MUST NOT independently redesign:

* the database;
* the publication system;
* the LLM architecture.

Scope expansion requires explicit authorization.

---

## 37. Principle XXXIV — Refactoring Requires Behavioral Preservation

Refactoring MUST preserve existing contracts.

Before refactoring:

```text
Existing Tests
        ↓
Refactor
        ↓
Same Behavioral Results
```

If behavior changes, the change is not merely refactoring.

It requires a specification update.

---

## 38. Principle XXXV — No Speculative Abstractions

The project SHOULD avoid abstractions created solely for hypothetical future requirements.

Avoid:

```text
GenericUniversalContentProviderFactory
```

when only one concrete provider exists.

Prefer:

```text
Clear current implementation
```

until genuine variation requires abstraction.

---

## 39. Principle XXXVI — Prefer Explicitness

The project SHOULD favor:

* explicit names;
* explicit types;
* explicit state transitions;
* explicit dependencies;
* explicit errors.

Over:

* implicit behavior;
* magic values;
* hidden side effects;
* undocumented conventions.

---

## 40. Principle XXXVII — Observability Is a Feature

Critical workflows MUST be observable.

The system SHOULD provide structured information about:

```text
Event Received
      ↓
Article Ingested
      ↓
Brief Generated
      ↓
Content Generated
      ↓
Validation Result
      ↓
Approval
      ↓
Publication
```

Each important stage SHOULD be traceable.

---

## 41. Principle XXXVIII — Auditability

The system MUST preserve a meaningful history of editorial automation.

Where applicable, the system SHOULD record:

* source article;
* generated versions;
* edits;
* approval decisions;
* publication attempts;
* final publication identifiers.

The system should support reconstruction of:

> what was generated, from which source, under which configuration, and what was ultimately published.

---

## 42. Principle XXXIX — Human Edits Are First-Class Data

Human modification of generated content MUST NOT be treated as an invisible overwrite.

The system SHOULD distinguish:

```text
AI Generated Version
        ↓
Human Edited Version
        ↓
Approved Version
        ↓
Published Version
```

Where feasible, versions should remain traceable.

---

## 43. Principle XL — Safe Retries

Retry mechanisms MUST NOT create duplicate effects.

Retryable operations SHOULD use:

* idempotency keys;
* publication state checks;
* bounded retry policies.

The system MUST distinguish:

```text
Retry
```

from:

```text
Repeat the business operation blindly
```

---

## 44. Principle XLI — External APIs Are Unreliable

The system MUST assume that external APIs may:

* timeout;
* rate-limit requests;
* return malformed responses;
* temporarily fail;
* change behavior.

External API integrations MUST implement appropriate:

* timeouts;
* error handling;
* retries where safe;
* logging.

---

## 45. Principle XLII — Accessibility Must Be Tested, Not Assumed

Accessibility claims MUST be supported by explicit checks where technically possible.

A feature MUST NOT be considered accessible merely because:

> the implementation appears reasonable.

Accessibility requirements should generate:

* acceptance criteria;
* automated checks;
* manual review requirements where automation is insufficient.

---

## 46. Principle XLIII — Definition of Done Is Enforceable

A feature is not complete merely because code executes.

Minimum Definition of Done:

* specification exists;
* acceptance criteria are satisfied;
* relevant tests pass;
* validation is implemented;
* errors are observable;
* documentation is updated;
* no secrets are introduced;
* architectural rules are respected.

---

## 47. Principle XLIV — Agents Must Verify Their Work

After implementation, an AI agent MUST perform verification against:

* the specification;
* acceptance criteria;
* existing tests;
* architectural constraints.

Preferred verification checklist:

```text
[ ] Scope respected
[ ] Specification implemented
[ ] Tests added
[ ] Tests passing
[ ] No architectural violation
[ ] No secrets introduced
[ ] Documentation updated
```

---

## 48. Principle XLV — Git History Is an Engineering Artifact

Changes SHOULD be:

* small;
* coherent;
* reviewable.

A commit SHOULD represent a meaningful engineering change.

Avoid combining:

* unrelated refactoring;
* new features;
* dependency upgrades;
* formatting changes;

in a single change set when separation improves reviewability.

---

## 49. Principle XLVI — CI Is a Constitutional Enforcement Layer

Continuous Integration SHOULD enforce relevant repository contracts.

The CI pipeline SHOULD eventually verify:

```text
Formatting
    ↓
Static Analysis
    ↓
Unit Tests
    ↓
Integration Tests
    ↓
Schema Validation
    ↓
Security Checks
```

CI SHOULD prevent known violations from reaching protected branches.

---

## 50. Principle XLVII — Fail Closed at Critical Boundaries

When critical validation is uncertain, the system SHOULD prefer:

```text
Do Not Publish
```

over:

```text
Publish Anyway
```

This principle applies particularly to:

* factual validation failures;
* invalid approval state;
* malformed publication payloads;
* missing required credentials;
* ambiguous publication status.

---

## 51. Principle XLVIII — Progressive Autonomy

Automation MAY increase over time.

However, autonomy must be introduced deliberately.

The progression is:

```text
Manual
   ↓
AI Assisted
   ↓
Human Approval
   ↓
Semi-Automated
   ↓
Selective Automation
```

The system MUST NOT jump to autonomous publication merely because automation is technically possible.

Each increase in autonomy requires explicit specification and risk analysis.

---

## 52. Principle XLIX — Metrics Must Not Override Editorial Integrity

Performance metrics MAY inform future optimization.

They MUST NOT become the sole optimization objective.

The system MUST NOT prioritize engagement over:

* factual integrity;
* accessibility;
* editorial standards;
* responsible communication.

---

## 53. Principle L — Prefer Reversible Decisions

When uncertainty exists, prefer decisions that are easier to reverse.

Examples:

* adapters over vendor coupling;
* configuration over hardcoded policies;
* explicit interfaces over hidden dependencies;
* modular components over monolithic workflows.

Irreversible decisions require greater scrutiny.

---

## 54. AI Agent Operating Protocol

Every AI agent working on the repository SHOULD follow this protocol.

## Phase 1 — Read

Read:

```text
Engineering Constitution
        ↓
Relevant Specification
        ↓
Relevant ADRs
        ↓
Existing Tests
        ↓
Relevant Code
```

---

## Phase 2 — Understand

Identify:

* objective;
* scope;
* constraints;
* invariants;
* dependencies.

---

## Phase 3 — Plan

Produce:

* implementation steps;
* affected files;
* new files;
* tests;
* risks.

---

## Phase 4 — Implement

Implement only the approved scope.

---

## Phase 5 — Test

Execute relevant tests.

---

## Phase 6 — Verify

Compare the result against:

* specification;
* acceptance criteria;
* constitutional principles.

---

## 55. Constitutional Invariants

The following invariants are mandatory.

## INV-001

Every generated social artifact MUST reference a source Article.

---

## INV-002

AI output MUST be validated before entering trusted application state.

---

## INV-003

Generated content MUST NOT directly trigger publication.

---

## INV-004

Publication MUST require a valid workflow state.

---

## INV-005

Duplicate external events MUST NOT produce duplicate business effects.

---

## INV-006

Editorial domain logic MUST NOT depend directly on platform SDKs.

---

## INV-007

Critical business rules MUST NOT exist exclusively inside prompts.

---

## INV-008

Secrets MUST NOT be committed to the repository.

---

## INV-009

Accessibility requirements MUST be included in feature acceptance criteria where applicable.

---

## INV-010

Major architectural decisions MUST be documented.

---

## 56. Constitutional Change Process

This Constitution may evolve.

Changes require explicit documentation.

A constitutional change SHOULD include:

1. motivation;
2. affected principles;
3. consequences;
4. migration considerations.

Constitutional changes SHOULD NOT be hidden inside unrelated commits.

---

## 57. Final Engineering Doctrine

The JincSAE is not built around the assumption that AI agents are reliable software engineers.

It is built around the assumption that:

> **AI agents are powerful but probabilistic collaborators operating within explicit technical, editorial, and architectural constraints.**

Therefore:

```text
AI provides acceleration.

Specifications provide direction.

Architecture provides boundaries.

Tests provide verification.

Validation provides protection.

Humans retain authority.
```

The central doctrine of the JincSAE is:

> **Move fast in implementation, but never move faster than the specifications, tests, validation boundaries, and editorial safeguards can support.**

---

> **End of Engineering Constitution**
