# Infrastructure Baseline

**Status**: Draft
**Phase**: 0 — Repository & Engineering Foundation

This document describes the initial architectural baseline for JincSAE infrastructure, aligned with ADR-002 (Persistence Strategy) and ADR-003 (Runtime and Queue Strategy).

## Cloud-Agnostic Overview

The infrastructure for JincSAE is designed to be cloud-agnostic in Phase 0. No specific cloud provider (e.g., AWS, GCP, Render) has been definitively chosen yet. This document maps out the required components and their deployment topologies.

### 1. API (Web Layer)

- **Role:** Handles incoming webhooks from WordPress, REST API endpoints, and validation.
- **Characteristics:** Stateless, horizontally scalable.
- **Requirements:** 
  - Ability to scale horizontally.
  - Access to the PostgreSQL database for synchronous operations.
  - Secret management for API keys and database credentials.

### 2. Transactional Outbox & PostgreSQL

- **Role:** Central persistence layer and source of truth for both application state and the event outbox.
- **Characteristics:** Stateful, high availability required.
- **Requirements:**
  - PostgreSQL instance.
  - Regular automated backups.
  - Support for `LISTEN/NOTIFY` (if applicable) or efficient polling for the outbox.

### 3. Outbox Relay

- **Role:** Dedicated background process that reads events from the Transactional Outbox table and pushes them into Procrastinate.
- **Characteristics:** Highly isolated, strict singleton or locking mechanism to avoid duplicate event dispatch.
- **Requirements:**
  - Continuous execution (long-running process).
  - Fast connection to PostgreSQL.

### 4. Procrastinate & Workers

- **Role:** Asynchronous task execution (editorial analysis, platform-specific generation, validation).
- **Characteristics:** Stateful tracking in PostgreSQL, horizontally scalable workers.
- **Requirements:**
  - Background worker processes listening to specific Procrastinate queues.
  - Graceful shutdown capabilities to not interrupt running AI generations.
  - Network access to external LLM APIs (OpenAI, Anthropic, etc.) and Social Media APIs.

### 5. CI/CD

- **Current State:** Baseline established using GitHub Actions (Linting, Type Checking, Testing).
- **Future State (Production Deployment):** Will require a pipeline that securely handles secrets, runs database migrations, and performs zero-downtime deployments for the API, Relay, and Workers.

### 6. Secrets & Configuration

- **Role:** Secure injection of environment variables.
- **Requirements:** 
  - Secrets must never be versioned.
  - In production, a secure vault or managed secrets service (e.g., AWS Secrets Manager, Doppler, GCP Secret Manager) will be chosen.
  - Local development uses `.env` files.

### 7. Logging & Observability

- **Role:** Traceability of asynchronous social media generation.
- **Requirements:**
  - Centralized structured logging (JSON).
  - Tracing for the journey: Webhook -> Outbox -> Worker -> Social API.
  - Error tracking (e.g., Sentry).

### 8. Environments

- **Local:** Docker Compose (PostgreSQL) + local virtual environments for API and Workers.
- **Staging:** A complete replica of the production architecture, potentially scaled down, connected to staging versions of external APIs or mocks.
- **Production:** The live environment serving Jornalista Inclusivo.

## Future Human Decisions Required

The following decisions are deferred and require human alignment in subsequent phases:

1. **Cloud Provider Selection:** Determine the definitive cloud provider and hosting model (e.g., PaaS vs. IaaS, Kubernetes vs. Managed Containers).
2. **PostgreSQL Hosting:** Managed DBaaS (e.g., Neon, RDS, Cloud SQL) vs. self-hosted.
3. **Observability Vendor:** Selection of error tracking and log aggregation tools.
4. **Secrets Manager:** Selection of the production secrets management solution.
