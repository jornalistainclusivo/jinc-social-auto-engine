# Product Requirements Document (PRD)

## Jornalista Inclusivo Social Automation Engine

**Status:** Draft
**Version:** 0.1.0
**Product Type:** Editorial Automation Platform
**Primary Language:** Portuguese (Brazil)
**Repository:** `jinc-social-engine`

---

## 1. Product Overview

### 1.1 Product Name

> **Jornalista Inclusivo (JINC) - Social Automation Engine**

Internal acronym:

> **JincSAE**

The system is an editorial automation engine designed to transform published articles from **Jornalista Inclusivo** into platform-specific social media content.

The product does not treat social media generation as a simple text-generation task. Instead, it implements a structured pipeline in which a published article becomes the canonical source for an editorial analysis process, followed by controlled transformations for each supported social platform.

The core pipeline is:

```text
Published Article
        │
        ▼
Content Ingestion
        │
        ▼
Editorial Analysis
        │
        ▼
Structured Editorial Brief
        │
        ├───────────────┐
        ▼               ▼
Platform-Specific Content Generation
        │
        ▼
Validation
        │
        ▼
Human Review / Approval
        │
        ▼
Publishing or Scheduling
        │
        ▼
Monitoring and Analytics
```

The initial supported platforms are:

* LinkedIn
* Facebook
* Instagram
* Bluesky

---

## 2. Problem Statement

Publishing an article does not automatically produce content suitable for distribution across social networks.

Each platform has distinct characteristics regarding:

* audience;
* discourse conventions;
* content length;
* interaction patterns;
* media formats;
* calls to action;
* discoverability mechanisms;
* temporal dynamics.

A manual workflow requires the editorial team to:

1. read or revisit the published article;
2. identify its central argument;
3. extract relevant information;
4. determine the appropriate editorial angle for each platform;
5. write multiple platform-specific versions;
6. adapt tone and structure;
7. verify factual consistency;
8. prepare visual assets where necessary;
9. publish or schedule the content;
10. monitor results.

This process is repetitive and operationally expensive.

At the same time, fully automated generic content generation creates significant editorial risks, including:

* factual hallucination;
* distortion of arguments;
* decontextualized quotations;
* incorrect attribution;
* repetitive messaging;
* platform-inappropriate content;
* inconsistent editorial voice;
* publication of sensitive content without review.

For a journalistic and accessibility-oriented publication, automation must therefore preserve:

> **editorial fidelity, traceability, accessibility, and human control.**

---

## 3. Product Vision

The Jornalista Inclusivo Social Automation Engine will provide an automated but controlled system for transforming published journalism into socially native content.

The system will treat the original article as the **canonical source of truth**.

All generated content must derive from information available in the source article or explicitly authorized editorial metadata.

The system should evolve from:

```text
Manual Social Media Production
```

toward:

```text
Article
   ↓
Structured Editorial Intelligence
   ↓
Platform-Specific Adaptation
   ↓
Validation
   ↓
Human Approval
   ↓
Automated Distribution
```

The long-term objective is to establish an **editorial content transformation infrastructure** rather than merely an AI copywriting tool.

---

## 4. Product Goals

### 4.1 Primary Goals

The system must:

1. detect newly published articles;
2. ingest article content and metadata;
3. generate a structured editorial representation of the article;
4. create platform-specific social media content;
5. preserve factual fidelity to the original article;
6. adapt language and structure to each platform;
7. validate generated content;
8. support human review and approval;
9. publish or schedule approved content;
10. maintain an auditable history of generated and published content.

---

### 4.2 Secondary Goals

The system should:

* reduce repetitive editorial work;
* improve consistency across social platforms;
* preserve the editorial identity of Jornalista Inclusivo;
* support accessibility-aware content generation;
* create reusable structured editorial data;
* enable future analytics-driven optimization;
* support experimentation with different editorial formats.

---

## 5. Non-Goals

The initial version of the system will **not**:

* autonomously create journalism;
* replace editorial judgment;
* rewrite articles without authorization;
* invent facts or sources;
* publish controversial or sensitive content without review;
* automatically respond to comments;
* perform autonomous community management;
* generate deceptive engagement content;
* impersonate human authors without explicit attribution policies;
* optimize content solely for engagement metrics.

The system is a **distribution and transformation layer**, not an autonomous newsroom.

---

## 6. Target Users

### 6.1 Primary User

#### Jornalista Inclusivo Editorial Administrator

Responsible for:

* reviewing generated content;
* approving or rejecting posts;
* editing generated content;
* configuring publication schedules;
* monitoring publication history.

---

### 6.2 Secondary Users

#### Journalist / Author

May:

* review generated content associated with their article;
* provide editorial metadata;
* approve or suggest modifications.

---

#### Social Media Manager

Responsible for:

* managing platform-specific strategy;
* reviewing publication queues;
* editing posts;
* monitoring performance;
* adjusting templates and policies.

---

#### System Administrator

Responsible for:

* API credentials;
* platform integrations;
* infrastructure;
* monitoring;
* security;
* backups.

---

## 7. Product Principles

### 7.1 Article as Source of Truth

The published article is the primary factual source.

Generated content must not introduce unsupported claims.

---

### 7.2 Transformation, Not Duplication

The same text must not simply be copied across platforms.

The system must perform:

```text
Editorial Transformation
```

rather than:

```text
Text Replication
```

---

### 7.3 Human Control

Automation should remain reversible and controllable.

The system must support:

* review;
* editing;
* approval;
* rejection;
* regeneration.

---

### 7.4 Accessibility by Design

Generated content must consider accessibility requirements and best practices, including:

* readable language;
* meaningful emoji usage;
* accessible image descriptions;
* avoidance of excessive decorative symbols;
* appropriate hashtag usage;
* caption support for audiovisual content;
* accessible formatting where supported.

---

### 7.5 Traceability

Every generated post should maintain a relationship with:

* the source article;
* the generation timestamp;
* the generation configuration;
* the platform;
* the approval status;
* the published version.

---

## 8. Core User Journey

### 8.1 Article Publication

A new article is published on WordPress.

```text
Draft
  │
  ▼
Published
  │
  ▼
Webhook Trigger
```

---

### 8.2 Content Ingestion

The system receives the publication event and retrieves:

* title;
* URL;
* publication date;
* author;
* article body;
* excerpt;
* categories;
* tags;
* featured image;
* relevant metadata.

---

### 8.3 Editorial Analysis

The article is analyzed to produce a structured editorial brief.

Example:

```json
{
  "central_thesis": "string",
  "summary": "string",
  "key_points": [
    "string"
  ],
  "relevant_quotes": [
    "string"
  ],
  "audiences": [
    "string"
  ],
  "topics": [
    "string"
  ],
  "editorial_tone": "string",
  "content_risk": "low"
}
```

---

### 8.4 Platform Generation

The structured brief is transformed into content appropriate for each platform.

```text
Editorial Brief
      │
      ├── LinkedIn Generator
      │
      ├── Facebook Generator
      │
      ├── Instagram Generator
      │
      └── Bluesky Generator
```

---

### 8.5 Validation

Generated content passes through validation layers.

```text
Generated Content
        │
        ▼
Schema Validation
        │
        ▼
Platform Validation
        │
        ▼
Editorial Validation
        │
        ▼
Accessibility Validation
        │
        ▼
Approval Queue
```

---

### 8.6 Human Review

The user may:

* approve;
* reject;
* edit;
* regenerate;
* schedule.

---

### 8.7 Publishing

Approved content is sent to the appropriate platform API.

```text
Approved Post
      │
      ▼
Platform Adapter
      │
      ▼
Social Network API
      │
      ▼
Publication Confirmation
```

---

## 9. Functional Requirements

## FR-001 — Article Detection

The system must detect newly published articles.

Supported detection mechanisms may include:

### Primary

WordPress webhook.

### Secondary

WordPress REST API polling.

The preferred event is:

```text
post_status_changed
```

or an equivalent transition:

```text
draft → publish
```

---

## FR-002 — Article Ingestion

The system must retrieve article data from WordPress.

Minimum required fields:

```text
id
title
url
content
excerpt
published_at
author
categories
tags
featured_image
```

---

## FR-003 — Canonical Article Storage

The system must store a normalized representation of the source article.

The stored article must maintain:

* WordPress post ID;
* canonical URL;
* publication timestamp;
* content hash;
* ingestion timestamp.

The content hash should support change detection.

---

## FR-004 — Editorial Analysis

The system must transform the article into a structured editorial brief.

The brief must identify, where applicable:

* central thesis;
* primary topic;
* key arguments;
* factual statements;
* quotations;
* relevant statistics;
* intended audiences;
* editorial tone;
* recommended social angles;
* potential sensitive content.

---

## FR-005 — Platform-Specific Generation

The system must generate independent content variants for each supported platform.

Initial platforms:

* LinkedIn;
* Facebook;
* Instagram;
* Bluesky.

Each generated object must preserve a reference to the source article.

---

## FR-006 — LinkedIn Content Generation

The LinkedIn generator should prioritize:

* professional relevance;
* analytical framing;
* contextualization;
* thought leadership;
* discussion prompts.

Possible structure:

```text
Hook

Context

Main Insight

Implications

Call to Action

Article URL
```

---

## FR-007 — Facebook Content Generation

The Facebook generator should prioritize:

* conversational accessibility;
* contextual summaries;
* shareability;
* audience engagement.

---

## FR-008 — Instagram Content Generation

The Instagram generator must support, at minimum:

### Caption

Including:

* introductory hook;
* concise context;
* central insight;
* call to action.

Future support may include:

* carousel scripts;
* image generation workflows;
* accessibility metadata;
* alt text.

---

## FR-009 — Bluesky Content Generation

The Bluesky generator must support:

* concise posts;
* article links;
* optional threads.

The generator must respect platform constraints configured by the platform adapter.

---

## FR-010 — Factual Validation

Generated content must be validated against the source article.

The system should identify:

* unsupported claims;
* altered statistics;
* fabricated quotations;
* incorrect attribution;
* misleading simplifications.

Posts that fail validation must not automatically enter the publishing stage.

---

## FR-011 — Accessibility Validation

The system must validate applicable accessibility criteria.

Initial checks may include:

* excessive emoji density;
* hashtag overload;
* readability;
* missing image descriptions;
* inaccessible formatting patterns.

---

## FR-012 — Human Approval

The system must support the following states:

```text
GENERATED
    │
    ├── EDITED
    │
    ├── APPROVED
    │
    ├── REJECTED
    │
    └── REGENERATED
```

Only approved content may enter the publishing queue.

---

## FR-013 — Content Editing

Users must be able to edit generated content before publication.

The system must preserve:

* original generated version;
* edited version;
* final published version.

---

## FR-014 — Scheduling

The system should support publication scheduling.

Each platform may have independent schedules.

Example:

```text
Article Published

LinkedIn → +30 minutes
Facebook → +2 hours
Instagram → +6 hours
Bluesky → immediate
```

Scheduling policies must be configurable.

---

## FR-015 — Publication

The system must publish approved content using platform-specific adapters.

The publishing layer must be separated from content generation.

```text
Generator
    ≠
Publisher
```

This separation enables testing and replacement of platform integrations.

---

## FR-016 — Publication Logging

The system must record:

* publication attempt;
* timestamp;
* platform;
* request status;
* platform publication ID;
* errors;
* retry history.

---

## FR-017 — Regeneration

Users must be able to regenerate content.

Regeneration may use:

* a different prompt configuration;
* a different editorial angle;
* a different content length;
* user-provided instructions.

Previous versions must remain available.

---

## FR-018 — Duplicate Prevention

The system must prevent duplicate publication.

A post should be identifiable by:

```text
article_id
+
platform
+
content_version
```

---

## FR-019 — Editorial Memory

The system should maintain structured information about previously published content.

Possible future uses include:

* avoiding repetitive hooks;
* identifying repeated themes;
* maintaining terminology consistency;
* remembering preferred calls to action;
* preserving platform-specific editorial conventions.

Editorial memory must not override the source article as the factual authority.

---

## 10. Non-Functional Requirements

## NFR-001 — Reliability

The system must tolerate:

* temporary API failures;
* network failures;
* webhook duplication;
* platform outages.

---

## NFR-002 — Idempotency

Webhook processing must be idempotent.

Receiving the same publication event multiple times must not generate duplicate publications.

---

## NFR-003 — Observability

The system must provide:

* structured logs;
* error logging;
* event tracing;
* publication history.

---

## NFR-004 — Security

Secrets must not be stored in source code.

Credentials must be managed through:

```text
Environment Variables
```

or an appropriate secret-management solution.

---

## NFR-005 — Maintainability

The system architecture must separate:

* ingestion;
* analysis;
* generation;
* validation;
* approval;
* publishing.

---

## NFR-006 — Testability

The system must support:

* unit testing;
* integration testing;
* contract testing;
* AI output evaluation.

---

## NFR-007 — Extensibility

Adding a new platform should not require modification of unrelated platform implementations.

The system should use a conceptual interface:

```python
class SocialPlatformAdapter:
    def generate(self, brief): ...

    def validate(self, content): ...

    def publish(self, content): ...
```

---

## 11. Editorial Content Model

The core product abstraction is the:

> **Editorial Brief**

The Editorial Brief separates:

```text
Article Understanding
```

from:

```text
Platform-Specific Writing
```

Conceptually:

```text
Article
   ↓
Editorial Brief
   ↓
Platform Adaptation
```

---

### 11.1 Editorial Brief Structure

```json
{
  "article_id": "string",

  "central_thesis": "string",

  "summary": "string",

  "key_points": [
    "string"
  ],

  "facts": [
    {
      "claim": "string",
      "source_location": "string"
    }
  ],

  "quotes": [
    {
      "text": "string",
      "speaker": "string"
    }
  ],

  "topics": [
    "string"
  ],

  "audiences": [
    "string"
  ],

  "editorial_angles": {
    "linkedin": "string",
    "facebook": "string",
    "instagram": "string",
    "bluesky": "string"
  },

  "risk_assessment": {
    "level": "low",
    "reasons": []
  }
}
```

---

## 12. Content Generation Model

Each generated post should be represented as structured data.

Example:

```json
{
  "id": "uuid",

  "article_id": "uuid",

  "platform": "linkedin",

  "content": "string",

  "hashtags": [
    "string"
  ],

  "url": "string",

  "status": "generated",

  "generated_at": "timestamp",

  "approved_at": null,

  "published_at": null
}
```

---

## 13. Validation Model

Validation must operate in layers.

### Layer 1 — Schema Validation

Checks:

* required fields;
* valid data types;
* valid platform identifier.

---

### Layer 2 — Platform Validation

Checks:

* character limits;
* required media;
* platform restrictions;
* formatting constraints.

---

### Layer 3 — Editorial Validation

Checks:

* factual fidelity;
* attribution;
* unsupported claims;
* misleading transformations.

---

### Layer 4 — Accessibility Validation

Checks:

* accessible text patterns;
* image metadata;
* readability;
* excessive visual clutter.

---

## 14. Approval Model

Initial approval strategy:

> **Human-in-the-loop**

Pipeline:

```text
GENERATED
    │
    ▼
VALIDATED
    │
    ▼
PENDING_REVIEW
    │
    ├──────────────┐
    ▼              ▼
APPROVED        REJECTED
    │
    ▼
SCHEDULED
    │
    ▼
PUBLISHED
```

---

## 15. Platform Architecture

Each platform must implement an independent adapter.

Conceptually:

```text
platforms/
│
├── linkedin/
│   ├── generator
│   ├── validator
│   └── publisher
│
├── facebook/
│   ├── generator
│   ├── validator
│   └── publisher
│
├── instagram/
│   ├── generator
│   ├── validator
│   └── publisher
│
└── bluesky/
    ├── generator
    ├── validator
    └── publisher
```

---

## 16. MVP Scope

The first Minimum Viable Product should include:

### Included

* WordPress article ingestion;
* webhook trigger;
* article storage;
* editorial brief generation;
* LinkedIn generation;
* Facebook generation;
* Instagram caption generation;
* Bluesky generation;
* validation;
* human approval;
* publication logging.

---

### Excluded from MVP

* autonomous publication;
* advanced analytics;
* automatic image generation;
* automatic carousel generation;
* automatic comment responses;
* predictive scheduling;
* performance-based content optimization.

---

## 17. Future Roadmap

### Phase 1 — MVP

```text
Article
↓
Analysis
↓
Generate Posts
↓
Review
```

---

### Phase 2 — Publishing

```text
Approval
↓
Scheduling
↓
Automatic Publishing
```

---

### Phase 3 — Visual Content

```text
Article
↓
Carousel Script
↓
Visual Generation
↓
Accessibility Metadata
```

---

### Phase 4 — Analytics

```text
Published Content
↓
Performance Data
↓
Editorial Analysis
```

Metrics may include:

* impressions;
* reach;
* clicks;
* shares;
* comments;
* saves;
* engagement rate.

---

### Phase 5 — Editorial Intelligence

Potential capabilities:

* content performance analysis;
* topic distribution;
* platform-specific learning;
* repetition detection;
* editorial pattern analysis.

---

## 18. Success Metrics

### Operational Metrics

* average time from publication to generated content;
* number of posts generated per article;
* approval rate;
* regeneration rate;
* manual editing rate.

---

### Quality Metrics

* validation failure rate;
* hallucination detection rate;
* duplicate publication incidents;
* editorial rejection rate.

---

### Efficiency Metrics

The system should demonstrate measurable reduction in:

```text
Manual Social Media Production Time
```

while preserving editorial quality.

---

## 19. Risks

### Risk: Hallucination

**Mitigation:**

* source-grounded generation;
* structured editorial briefs;
* factual validation;
* human approval.

---

### Risk: API Changes

Social media APIs may change.

**Mitigation:**

* isolated platform adapters;
* contract testing;
* versioned integrations.

---

### Risk: Duplicate Publications

**Mitigation:**

* idempotency;
* publication state tracking;
* unique identifiers.

---

### Risk: Editorial Homogenization

AI-generated content may become repetitive.

**Mitigation:**

* editorial memory;
* variation strategies;
* human review.

---

### Risk: Accessibility Regression

Generated content may introduce inaccessible practices.

**Mitigation:**

* accessibility validation;
* structured content rules;
* human review.

---

## 20. Proposed Technology Direction

Initial proposed stack:

| Layer           | Technology            |
| --------------- | --------------------- |
| Language        | Python                |
| IDE             | Antigravity / VS Code |
| API             | FastAPI               |
| Validation      | Pydantic              |
| Testing         | pytest                |
| CMS Integration | WordPress REST API    |
| Database        | PostgreSQL            |
| ORM             | SQLAlchemy            |
| Queue           | Redis                 |
| Background Jobs | Celery or equivalent  |
| Containers      | Docker                |
| CI/CD           | GitHub Actions        |

The final technology choices must be documented in the Software Design Document and Architecture Decision Records.

---

## 21. Development Methodology

The project should follow a hybrid methodology:

```text
PRD
 ↓
SDD
 ↓
Architecture
 ↓
ADRs
 ↓
Technical Specifications
 ↓
Acceptance Criteria
 ↓
Tests
 ↓
Implementation
```

---

## 21.1 PRD

Defines:

> What the product must accomplish.

---

## 21.2 SDD

Defines:

> How the system will be designed.

---

## 21.3 ADRs

Define:

> Why specific architectural decisions were made.

---

## 21.4 Specifications

Define:

> The behavioral contract of individual components.

---

## 21.5 TDD

Defines the implementation cycle:

```text
Test
 ↓
Fail
 ↓
Implement
 ↓
Pass
 ↓
Refactor
```

For AI-generated content, tests should prioritize:

* structural properties;
* factual grounding;
* platform constraints;
* validation outcomes.

Exact textual equality should generally not be used as the primary testing strategy.

---

## 22. Acceptance Criteria for MVP

The MVP will be considered successful when the system can:

* detect a newly published WordPress article;
* ingest its canonical content;
* generate a structured editorial brief;
* generate content for all four initial platforms;
* validate generated content;
* present content for human approval;
* store approval decisions;
* prevent duplicate processing;
* maintain publication history.

---

## 23. Open Questions

The following decisions remain open and should be resolved during the SDD phase:

1. Will WordPress use a custom webhook plugin or an existing webhook mechanism?
2. Where will the approval interface be hosted?
3. Will the first version include direct publishing APIs or only content generation?
4. Which LLM provider(s) will be supported?
5. Will editorial prompts be stored in the repository or database?
6. How will sensitive journalistic content be classified?
7. How will image and carousel workflows be integrated?
8. Which analytics data should be stored?
9. What is the retention policy for article and generated content data?
10. How will editorial memory be governed?

---

## 24. Definition of Done

A feature is considered complete when:

* its specification exists;
* acceptance criteria are defined;
* automated tests pass;
* validation rules are implemented;
* errors are logged;
* documentation is updated;
* no secrets are committed to the repository;
* the feature is integrated into the application architecture.

---

## 25. Final Product Principle

The Jornalista Inclusivo Social Automation Engine must not function as an autonomous content factory.

Its fundamental purpose is to provide:

> **A reliable, accessible, traceable, and editorially controlled infrastructure for transforming published journalism into platform-specific social communication.**

The article remains the canonical source.

Artificial intelligence performs structured transformation.

Validation protects editorial integrity.

Human judgment retains final authority.

```text
Journalism
    ↓
Editorial Intelligence
    ↓
Controlled Transformation
    ↓
Accessible Distribution
```

---

> **End of PRD**
