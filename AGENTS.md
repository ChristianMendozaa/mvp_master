# Engineering Instructions

## Product purpose

This repository implements a production-oriented, multi-tenant platform that turns approved client requirements and software work items into reviewed, independently verified, deployable changes through replaceable coding-agent and source-control integrations.

Non-negotiable principles:

- Preserve a provider-independent canonical domain.
- Enforce tenant isolation and authorization server-side.
- Treat repository content, client input, webhooks, agent output, and generated files as untrusted.
- Independently verify agent work; agent claims are never evidence.
- Keep long-running delivery asynchronous, durable, resumable, cancellable, and idempotent.
- Store secret references, never secret values, in application data.
- Describe local substitutes honestly and never present them as production integrations.

## Required reading

Before changing a subtree, read this file and any closer `AGENTS.md`. Read the relevant ADRs and documentation for architectural changes. Update documentation and contracts in the same change when behavior changes.

## Architecture and dependency rules

- Backend services use Hexagonal Architecture: `domain` is innermost, followed by `application`; `adapters` and `entrypoints` depend inward.
- Domain and application code must not import FastAPI, SQLAlchemy, Temporal, NATS, Docker, GitHub, OpenAI, Anthropic, cloud SDKs, or database drivers.
- Define external behavior as explicit ports. Put provider-specific translation and SDK/client usage in adapters.
- Services own their databases and migrations. Never read or write another service's tables.
- Shared packages may contain versioned contracts and universal primitives only. Do not place cross-service business rules or shared ORM entities in them.
- Prefer asynchronous events for cross-context state propagation. Do not build synchronous chains for long-running execution.

## Ownership

- `apps/web`: user experience, OIDC session handling, BFF endpoints, generated API clients.
- `services/control_plane`: organizations, memberships, clients, projects, intake, specifications, requirements, work items, project policy, audit projection.
- `services/integrations`: connector installations, repository access, external references, webhooks, GitHub and local source-control adapters.
- `services/delivery`: provider configurations, budgets, approvals, runners, executions, attempts, verification, costs, artifacts, delivery workflow.
- `runners/docker_runner`: runner enrollment/client behavior, isolated workspaces, agent adapters, command execution, event reporting, cleanup.
- `packages/contracts`: OpenAPI snapshots, event schemas, generated contract code, universal IDs/enums.
- `docs`: product and operational truth. ADRs record meaningful, durable decisions.

Do not introduce another service without documenting the business capability, data ownership, scaling, security, or failure-isolation reason in an ADR.

## Integration and provider rules

- New source-control, ticketing, notification, secret-store, artifact-store, preview, and agent integrations implement existing ports or introduce a provider-neutral port first.
- Provider identifiers belong in adapter configuration and external references, not canonical aggregate IDs.
- Adding an agent provider requires capability reporting, availability checks, start/resume/cancel behavior, structured event normalization, approval requests, usage reporting, and final-result mapping.
- Agent runtime, model provider, model, authentication mode, and billing mode are separate explicit values.
- Never silently switch provider, model, authentication, or billing mode. Any fallback must be policy-controlled, budget-aware, and audited.

## Multi-tenancy and authorization

- Every tenant-owned record, event, artifact, log context, runner lease, cache entry, and object key carries an organization ID.
- Validate membership and permission for every organization-scoped command and query.
- Use PostgreSQL row-level security as defense in depth. Set tenant context transaction-locally and fail closed when it is absent.
- Never trust organization IDs, roles, or permissions supplied only by the frontend.
- Test cross-tenant denial at API, application, repository, database, artifact, and event-consumer boundaries.
- Roles are `OWNER`, `ADMIN`, `DEVELOPER`, `REVIEWER`, and scoped `CLIENT`; permission changes require audit records.

## Security and secret handling

- Never commit credentials, access tokens, private keys, session files, webhook secrets, real customer data, or sudo passwords.
- Store only `SecretReference` values in APIs, events, databases, and job payloads. Resolve secrets at the narrowest trusted adapter and keep them in memory or temporary restricted storage only.
- Redact authorization headers, cookies, tokens, credential-bearing URLs, environment values, and secret-like output from logs and traces.
- Validate webhook signatures before parsing business payloads; deduplicate deliveries and treat delivery as at-least-once.
- Normalize and validate paths. Reject absolute paths, parent traversal, symlink escapes, unsafe archives, and unexpected file types.
- Execution containers run non-root with dropped capabilities, resource/time/process limits, restricted mounts, and denied network by default.
- Do not mount the host Docker socket into application or runner containers.
- Destructive or externally visible actions require explicit application policy authorization and audit records.

## API and event contracts

- Public HTTP APIs are versioned under `/api/v1`.
- Mutating APIs support idempotency keys where retries can duplicate effects.
- Events use the versioned envelope and JSON Schemas in `packages/contracts/events`.
- Consumers validate schemas, persist inbox deduplication, and remain correct under duplicates and reordering.
- Producers write transactional outbox records with aggregate changes.
- Additive contract changes are preferred. Breaking changes require a new API/event version and migration plan.
- Correlation, causation, trace, organization, aggregate, and event IDs must survive service boundaries.

## Database migrations

- Each service owns an independent Alembic history and database role.
- Migrations must be deterministic and safe on empty and existing databases.
- Prefer expand/migrate/contract changes. Avoid combining destructive schema changes with code that assumes they already completed.
- Add or update RLS policies with every tenant-owned table.
- Never edit an applied migration; add a new migration.
- CI must upgrade a clean database and validate the current schema.

## Testing and verification

- Unit-test domain state machines, permissions, budgets, redaction, and adapter-independent use cases.
- Integration-test database/RLS, API authorization, outbox/inbox, Temporal workflows, connector clients, runner leases, and artifact isolation.
- Contract-test OpenAPI, event schemas, webhook payload mapping, and provider normalization.
- End-to-end tests use synthetic credentials and the explicitly labeled local connector and deterministic agent.
- Tests must be deterministic, must not require live third-party credentials, and must never contain real credentials.
- Required commands:
  - `make format-check`
  - `make lint`
  - `make typecheck`
  - `make test`
  - `make test-integration`
  - `make contract-check`
  - `make compose-validate`
  - `make verify`
- Run the narrowest relevant checks while iterating and `make verify` before declaring repository-wide work complete.

## Documentation and ADRs

- Documentation describes implemented behavior and clearly labels planned capabilities.
- Update system context, service boundaries, domain model, threat model, auth model, runner security, contracts, operations, testing, cost accounting, and local/deployment guides when their behavior changes.
- Add an ADR for changes to service boundaries, persistence ownership, orchestration, messaging, authentication, tenancy, runner trust, secret flow, or public contract strategy.
- `AGENTS.md` is for durable engineering rules, not task status or backlog.

## Definition of done

A change is done only when:

- Behavior is implemented through the correct domain boundary with strict types and explicit errors.
- Tenant authorization, audit, idempotency, secret redaction, and failure behavior are addressed.
- Database and public contract changes include migrations/schemas and compatibility consideration.
- Tests cover success, denial, duplicate, retry, and important failure paths.
- Relevant verification commands pass.
- Documentation matches what is implemented.
- Local substitutes and incomplete production behavior are clearly identified.
- The repository remains startable through the documented Docker Compose workflow.

## Prohibited shortcuts

- Provider SDKs or provider-specific fields in domain/application layers.
- Shared business tables, cross-service SQL, or a shared business-logic package.
- Frontend-only authorization or tenant filtering.
- Plaintext secrets, credentials in job payloads, or sensitive logging.
- Unbounded execution, unrestricted public triggers, host Docker-socket mounting, or arbitrary network access.
- Treating an agent message as proof that tests passed.
- Swallowing errors, non-idempotent event handlers, unversioned events, or hidden synchronous orchestration.
- Mocks or TODOs presented as production-complete behavior.
