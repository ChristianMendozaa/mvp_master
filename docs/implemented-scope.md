# Implemented scope

This document is updated with each increment and is the source of truth for product claims.

## Current

- Durable root engineering instructions, service ownership rules, and seven ADRs.
- A locked Python/pnpm monorepo with strict lint, format, type, unit-test, contract,
  Compose-validation, build, and dependency-audit gates.
- Local Keycloak OIDC Authorization Code + PKCE login, HTTP-only token cookies, a
  same-origin BFF, organization roles, and server-side membership checks.
- Control-plane organization, project, structured intake, immutable specification
  version, approval, work-item review, and readiness workflows.
- A provider-neutral source-control port with a clearly labeled local GitHub
  substitute. A GitHub REST adapter and signed, deduplicated webhook ingress exist,
  but production App installation and credential minting are not wired.
- Provider configuration that keeps provider, runtime, model, authentication mode,
  and secret reference explicit. The deterministic runtime is runnable. A Codex CLI
  adapter exists but its binary/session and secret resolver are not packaged in the
  local job image.
- One-use runner enrollment, hashed runner credentials, expiring/heartbeat-backed
  job leases, a constrained Docker job container, a separate read-only/no-network
  validation container, bounded repair, and cleanup.
- Transactional outboxes, versioned JetStream events, inbox deduplication, and a
  Temporal workflow with approval and cancellation signals.
- Per-service PostgreSQL databases, tenant columns, forced row-level security,
  automated Alembic migrations, append-only audit tables, JSON logging, and OTLP
  instrumentation.
- A responsive Next.js workflow UI with approval actions, budget display, execution
  timeline over SSE, verification status, and simulated pull-request links.
- Generated and reviewed OpenAPI snapshots plus versioned JSON Schema event contracts.

## Explicitly not production-complete in this slice

- Managed cloud infrastructure and hardened sandbox runtime.
- Claude/Anthropic adapters, provider fallback and enterprise provider policy.
- Anonymous or magic-link client intake.
- Preview-provider deployment.
- Enterprise secret-store resolution and credential leases.
- Real repository clone/branch/push, GitHub App installation callbacks, temporary
  installation-token minting, Issue/comment/check synchronization, and installation
  lifecycle reconciliation.
- Durable artifact-object storage and full token/tool-call/price-catalog accounting.
- Execution-level PostgreSQL/Temporal replay tests and a continuously exercised
  Compose/Playwright path in CI. The complete path is checked in and has been
  exercised locally, but is not yet a CI job.
- Live third-party certification tests without operator-supplied credentials.

The local connector and deterministic agent are development substitutes and must be labeled as such in APIs, UI, logs and documentation.
