# Implemented scope

This document is updated with each increment and is the source of truth for product claims.

## Current

- Durable root engineering instructions, service ownership rules, and nine ADRs.
- A locked Python/pnpm monorepo with strict lint, format, type, unit-test, contract,
  Compose-validation, build, and dependency-audit gates.
- Local Keycloak OIDC Authorization Code + PKCE login, HTTP-only token cookies, a
  same-origin BFF, organization roles, and server-side membership checks.
- Control-plane organization, project, structured intake, immutable specification
  version, approval, work-item review, and readiness workflows.
- A provider-neutral source-control port with a clearly labeled local substitute and
  an opt-in GitHub.com App flow: operator manifest registration, encrypted secret
  references, tenant installation proof, paginated reconciliation, signed webhooks,
  ephemeral repository credentials, clone/push/PR, and verification check runs.
- Provider configuration that keeps provider, runtime, model, authentication mode,
  and secret reference explicit, validated against a reviewed compatibility table
  (`services/delivery/.../domain/agent_runtimes.py`) at create time. Four runnable
  agent runtimes: `deterministic` (development substitute), `codex-cli` (Codex CLI,
  both API-key and ChatGPT-subscription auth — also serves the Codex SDK, which
  wraps the same binary), `claude-code-cli` (Claude Code CLI, both API-key and
  Claude-subscription auth, and — via a reviewed provider catalog — Anthropic-
  compatible third-party providers including Zhipu GLM and Moonshot Kimi), and
  `claude-agent-sdk` (the Python Claude Agent SDK, API-key only per Anthropic's
  terms). All four are packaged in the job image (Node.js + `claude`/`codex` CLIs +
  `claude-agent-sdk`).
- A model-credential lease mirroring the Git source-credential flow: a short-lived,
  single-use, job-scoped capability minted by delivery and redeemed once by the
  runner daemon (never the sandboxed agent process) against the existing encrypted
  file secret store; the resolved value is injected only as a job-container
  environment variable.
- Scoped model-provider network egress: real-agent job containers get network access
  restricted to exactly one allowlisted provider host via a fail-closed internal
  Docker network and CONNECT proxy, off by default
  (`AGENT_EGRESS_ENABLED=false`) and never applied to `deterministic` or the
  validator container.
- One-use runner enrollment, hashed runner credentials, expiring/heartbeat-backed
  job leases, a constrained Docker job container, a separate read-only/no-network
  validation container, bounded repair, and cleanup.
- Transactional outboxes, versioned JetStream events, inbox deduplication, and a
  Temporal workflow with approval and cancellation signals.
- Per-service PostgreSQL databases, tenant columns, forced row-level security,
  automated Alembic migrations, append-only audit tables, JSON logging, and OTLP
  instrumentation.
- A responsive Next.js first-use wizard that guides GitHub App setup/installation,
  repository discovery, reviewed agent/model selection, write-only API-key storage,
  isolated provider probing, and runner readiness. The workflow UI requires explicit
  repository, verified provider, and runner selections and retains approval actions,
  budget display, execution timeline over SSE, verification status, and pull-request
  references.
- Generated and reviewed OpenAPI snapshots plus versioned JSON Schema event contracts.

## Explicitly not production-complete in this slice

- Managed cloud infrastructure and hardened sandbox runtime.
- Live-credential CI certification for any real agent runtime (`codex-cli`,
  `claude-code-cli`, `claude-agent-sdk`) — the adapters and their unit tests never
  use live credentials or network, matching AGENTS.md, and no automated pipeline
  runs them against a real provider account.
- Agent-runtime session resume and an approval round-trip (`supports_resume` /
  `supports_approval` are honestly reported as unsupported on every real runtime in
  this increment; only `codex-cli` advertises both but the mapping is best-effort).
- Provider fallback and enterprise provider policy (never silently substituting a
  provider, model, or auth mode — see AGENTS.md — is enforced; automatic fallback
  between providers is not implemented).
- An enterprise-grade secret store (KMS/HSM/Vault-backed). Model and source
  credentials both use the same encrypted-file store; the credential-lease
  *mechanism* (short-lived, single-use, job-scoped capabilities) is implemented for
  both, but the underlying store is still the local encrypted-file adapter.
- Anonymous or magic-link client intake.
- Preview-provider deployment.
- GitHub Enterprise Server, Issue/comment intake, forks, submodules, LFS, workflow
  file changes, automatic merge, and a managed enterprise secret store.
- Durable artifact-object storage and a price catalog. Token counts (input/cached/
  output) now flow from agent adapters through to execution events; monetary
  `cost_minor` is still hardcoded to 0 pending a price catalog.
- Execution-level PostgreSQL/Temporal replay tests and a continuously exercised
  Compose/Playwright path in CI. The complete path is checked in and has been
  exercised locally, but is not yet a CI job.
- Live third-party certification tests without operator-supplied credentials.

The local connector and deterministic agent are development substitutes and must be
labeled as such in APIs, UI, logs and documentation. Real agent runtimes
(`codex-cli`, `claude-code-cli`, `claude-agent-sdk`) require both an
organization-submitted model credential and `AGENT_EGRESS_ENABLED=true` on the
runner — neither is on by default, and a job that requests a real runtime without
both fails loudly rather than silently falling back to a substitute.
