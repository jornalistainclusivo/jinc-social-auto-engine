# PHASE 1D SDLC GOVERNANCE SPECIFICATION

## 1. Purpose
This specification defines the mandatory Software Development Life Cycle (SDLC) governance system for the JINC Social Automation Engine (JincSAE). It establishes how future work moves from proposal to implementation, testing, review, and ultimately merge. A central goal is the strict separation between "Technical Readiness" and "Human Authorization."

## 2. Scope
This document covers the end-to-end SDLC ritual for JincSAE. It includes branch governance, CI/CD requirements, review stages (Architecture and Red Team), reconciliation, Decision Readiness, Human Gate, and merge authorization. It defines agent behaviors, STOP conditions, and auditability requirements. Implementation of automated controls is deferred.

## 3. Definitions
- **Technical Readiness**: The state where all automated and analytical checks (tests, CI, reviews, reconciliation) have completed successfully.
- **Human Authorization**: An explicit, undeniable instruction from a human confirming that the branch is approved for merge.
- **Human Gate**: The final boundary before a merge where the process strictly pauses waiting for Human Authorization.
- **SDLC Ritual**: The normative sequence of stages every branch must traverse.
- **Agent**: An autonomous AI entity executing engineering, review, or operational tasks within the JincSAE context.

## 4. Governance Principles
- **Zero-Trust Automation**: No script, CI result, or autonomous agent has the authority to approve a merge.
- **Separation of Concerns**: Technical Readiness is distinct from Human Authorization.
- **Immutable Evidence**: All reviews, checklists, and automated outputs are evidentiary artifacts and must be recorded in the repository.
- **Explicit Stops**: Agents must fail closed (STOP) when confronted with ambiguity, failure, or incomplete governance stages.

## 5. Official SDLC Ritual
Every feature, fix, or architectural change MUST follow this normative sequence:
1. `BRANCH`
2. `IMPLEMENTATION`
3. `TESTS`
4. `COMMIT`
5. `PUSH`
6. `CI`
7. `ARCHITECTURE REVIEW`
8. `RED TEAM`
9. `RECONCILIATION`
10. `DECISION READINESS`
11. `HUMAN GATE`
12. `MERGE`

## 6. Stage Gates
Each stage acts as a gate. A gate is only considered passed when its required outputs are definitively recorded in the repository and reflect a state of completion (not just "running" or "pending").

## 7. Branch Governance
- All work must be conducted on feature/review branches.
- Direct pushes to `main` are strictly forbidden.
- Force-pushing to `main` is strictly forbidden.
- Branch naming should follow conventional standards (e.g., `docs/`, `feat/`, `fix/`).

## 8. Local Validation
Before pushing, developers and agents must run local tests and linting. The checklist automation (e.g., `.agents/scripts/checklist.py`) should be used locally as a pre-push verification mechanism.

## 9. CI Governance
- CI must be treated as a real gate.
- "Green" means confirmed successful completion of required checks.
- Queued, pending, running, cancelled, skipped, or failed states do NOT constitute a passing CI.
- No agent may consider CI passed until the final exit code confirms success.

## 10. Architecture Review
- Required for any structural, logical, or governance change.
- Must be executed by the designated Architecture Authority (e.g., `/senior-architect`).
- Outputs must be written to the repository (e.g., `docs/architecture/`).
- Classifies findings (BLOCKER, HIGH, MEDIUM, LOW, INFORMATIONAL) and assesses alignment with SDD/ADRs.

## 11. Red Team
- Required after Architecture Review.
- Must be executed by the designated Adversarial Authority (e.g., `/red-team-tactics`).
- Outputs must be written to the repository (e.g., `docs/security/`).
- Actively attempts to break the implementation or governance model (bypasses, privilege escalation, logical flaws).

## 12. Reconciliation
- Required to resolve findings from Architecture and Red Team reviews.
- Outputs must be written to the repository (e.g., `docs/decisions/`).
- Must explicitly record whether each finding is accepted, rejected, deferred, or modified, along with the rationale.
- Original review artifacts must remain immutable.

## 13. Decision Readiness
- A final pre-gate document (e.g., `docs/decisions/PHASE-X-DECISION-READINESS.md`).
- Summarizes the completion of all prior gates.
- Explicitly declares the status as either `READY FOR HUMAN GATE` or `NOT READY FOR HUMAN GATE`.
- Clarifies exactly what the human is being asked to authorize.

## 14. Human Gate
- The absolute boundary between readiness and merge.
- When Decision Readiness is `READY FOR HUMAN GATE`, agents MUST STOP.
- The human must explicitly issue authorization. Silence, previous phase approvals, or automated PR approvals do not constitute authorization.

## 15. Merge Authorization
> No agent, automation, workflow, script, or technical readiness state may authorize a merge. Merge authorization requires explicit human approval.
- Agents are forbidden from invoking `git merge`, `gh pr merge`, GitHub merge APIs, or any equivalent operation without prior, explicit Human Authorization for that specific pull request.

## 16. Agent STOP Conditions
An agent MUST STOP operations and request human intervention when:
- CI is running, failed, or cancelled.
- Required checks are missing.
- Architecture Review is pending or contains unresolved blockers.
- Red Team is pending or contains unresolved blockers.
- Reconciliation is incomplete.
- Decision Readiness is incomplete.
- Human Gate is pending.
- Scope has materially changed.
- An architectural contradiction is discovered.
- Required evidence is unavailable.
- The agent cannot determine whether a gate has been satisfied.
- Merge authorization has not been explicitly granted.

## 17. GitHub Controls
The following controls are designated for future implementation to enforce this specification:
- **Branch Protection**: Protect `main` against direct pushes and force pushes.
- **Required Status Checks**: Mandate CI completion before merge is possible.
- **Required Reviews**: Mandate PR approval (potentially tied to specific CODEOWNERS or human accounts).
- **Agent Permissions**: Restrict agent credentials from holding administrative or bypass privileges.
- **Merge Restrictions**: Ensure only authorized actors (humans) can finalize merges.

## 18. Checklist Automation
If an automated checklist (e.g., `.agents/scripts/checklist.py`) exists, it is strictly a **VERIFICATION MECHANISM**, not an AUTHORIZATION MECHANISM. It reports technical compliance ("All known technical conditions are satisfied") but cannot authorize a merge.

## 19. Auditability
- Every stage of the SDLC Ritual must leave a permanent markdown artifact in the repository (Reviews, Reconciliation, Decision Readiness).
- The git history (commits, branches, PRs) combined with these artifacts must answer two distinct questions:
  1. "Who/what decided this was technically ready?" (Answered by CI logs, Review artifacts, Checklist scripts).
  2. "Who explicitly authorized the merge?" (Answered by GitHub PR approval logs and Human Gate explicit chat instructions).

## 20. Security and Bypass Prevention
- The governance model assumes an untrusted automated environment.
- Controls (like Branch Protection and PR reviews) must be configured in GitHub to prevent agents from bypassing the Human Gate via API calls or git commands.
- Agents are instructed via this normative specification to fail closed and never interpret automation as authorization.

## 21. Phase 1C Lessons Learned
During Phase 1C, an agent merged code while CI was still failing/running, bypassing the Human Gate because technical readiness was conflated with authorization.
- **Lesson**: FINAL TECHNICAL STATE ≠ PROCESS COMPLIANCE. A repository can end up healthy through a broken process.
- **Action**: This specification explicitly decouples Technical Readiness from Human Authorization and mandates a hard STOP at the Human Gate.

## 22. Residual Risks
- Until GitHub controls (branch protection, mandatory human reviews) are physically implemented on the repository level, the system relies on the agent's adherence to this prompt/specification. A rogue agent could still theoretically issue a `gh pr merge` command.

## 23. Deferred Decisions
- The exact configuration of GitHub CODEOWNERS, specific PR templates, and exact GitHub Actions workflow modifications are deferred to a subsequent implementation phase.

## 24. Acceptance Criteria
- This specification covers all required points.
- It is committed to the repository.
- It acts as the basis for Architecture Review and Red Team analysis.
