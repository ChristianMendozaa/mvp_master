# CLAUDE.md

This file gives an AI coding agent the operational context needed to work in this
repository. It does not restate engineering rules — **read [`AGENTS.md`](AGENTS.md)
first**; it is the durable source of truth for architecture rules, ownership,
security requirements, and the definition of done. This file is navigation and
pitfalls: where things live, what commands to run, and what has already caused
mistakes here.

Before claiming any capability exists or works a certain way, check
[`docs/implemented-scope.md`](docs/implemented-scope.md). It is updated with every
increment and takes precedence over any other document, including this one, if they
disagree.

## Repository map

- `apps/web` — Next.js UI and BFF. Browser calls go through
  `src/app/api/bff/[service]/[...path]/route.ts`, which maps `control` /
  `integrations` / `delivery` to the three backend base URLs, attaches the bearer
  token from an HTTP-only cookie, and enforces CSRF/same-origin checks on mutating
  methods. OIDC helpers are in `src/lib/auth.ts`; CSRF/PKCE primitives are in
  `src/lib/security.ts`.
- `services/control_plane` — organizations, memberships, clients, projects, intake,
  specifications, requirements, work items, project policy, audit projection.
- `services/integrations` — connector installations, repository access, external
  references, webhooks, GitHub and local source-control adapters.
- `services/delivery` — provider configurations, budgets, runners, executions,
  attempts, verification, costs, artifacts, the delivery Temporal workflow.
- `runners/docker_runner` — independently deployable worker: runner
  enrollment/client, isolated workspaces, agent adapters, command execution, event
  reporting, cleanup.
- `packages/contracts` — versioned OpenAPI snapshots (`openapi/`) and event JSON
  Schemas (`events/`). Treat these as generated/reviewed artifacts, not hand-authored
  documentation.
- `packages/python_common` — `SecretReference`, `ExternalReference`, `EventEnvelope`,
  log redaction, ID helpers. Universal primitives only — never cross-service business
  rules.
- `packages/python_observability` — shared OpenTelemetry wiring for the FastAPI
  services.
- `docs` — product and operational truth; `docs/adrs` — durable architecture
  decisions with consequences.

Do not introduce a new service without an ADR documenting the business capability,
data ownership, scaling, or failure-isolation reason (`AGENTS.md`).

## Layer layout, in practice

Every Python deployable (the three services and the runner) follows:

```text
domain <- application <- adapters <- entrypoints
```

- `domain/models.py` — frozen or slotted dataclasses, `StrEnum` status types, guard
  methods that raise a domain error on an invalid transition (e.g.
  `Execution.request_repair` in `services/delivery/.../domain/models.py`). No I/O.
- `domain/errors.py` — the domain's own exception types.
- `application/ports.py` — `typing.Protocol` definitions for everything external
  (storage, workflow gateway, agent runtime, secret resolver).
- `application/service.py` — use cases that depend only on ports, never on a
  concrete adapter.
- `adapters/` — one file per external system: `postgres.py`, `memory.py` (for
  tests), `oidc.py`, `temporal_workflow.py`, `github.py`, `docker_agent.py`. All
  provider SDK usage and framework-specific translation lives here.
- `entrypoints/` — `api.py` (FastAPI), `events.py` (JetStream consumer), `outbox.py`
  or `workflow_dispatcher.py` / `workflow_worker.py`. This is where dependencies are
  assembled and transport is exposed.

The enforced rule: **domain and application code must not import FastAPI,
SQLAlchemy, Temporal, NATS, Docker, GitHub, or any model-provider SDK.** This is not
caught by `mypy --strict` or `ruff` today — it is a review-time check. If you add an
import like this at the wrong layer, move the logic behind a port instead.

## Commands, narrowest first

Prefer the smallest command that exercises what you changed; run `make verify`
before declaring repository-wide work complete (this matches `AGENTS.md`'s
"Definition of done").

```bash
# One package/service at a time (fast feedback while iterating)
cd services/delivery && uv run pytest
cd services/delivery && uv run mypy src
cd services/delivery && uv run ruff check src

# Repository-wide, in the order CI expects
make format-check
make lint
make typecheck
make test
make contract-check
make migration-check
make compose-validate
make verify            # runs all of the above except test-integration/test-e2e

# Infrastructure-backed (needs `make up` first)
make test-integration
make test-e2e
```

Notes that have tripped things up before:

- Python is pinned to `>=3.13,<3.14` (`pyproject.toml`); a different local
  interpreter will produce spurious type/behavior differences.
- `pytest` runs with `asyncio_mode = "auto"` — async test functions do not need
  `@pytest.mark.asyncio`.
- mypy is `strict` with `warn_unreachable = true` — an unreachable `else` after an
  exhaustive `StrEnum` match will fail typecheck, not just lint.
- Ruff has `S` (bandy security) rules enabled repository-wide except `S101`; a
  deliberate exception needs an explicit `# noqa: S1xx` with justification, as in
  `docker_agent.py`'s `# noqa: S108` on a tmpfs path.

## Making common changes

- **New use case** — add a guarded method on the domain aggregate, extend the port
  in `application/ports.py` only if it needs something external, implement it in the
  adapter, wire it in the entrypoint.
- **New HTTP endpoint** — add the route in `entrypoints/api.py`, then regenerate and
  review the contract snapshot:
  ```bash
  uv run python scripts/export_openapi.py --write
  make contract-check
  ```
  Skipping this fails CI with a stale-snapshot error, not a helpful diff.
- **New domain event** — add a versioned JSON Schema under
  `packages/contracts/events/`, write the aggregate change and an outbox row in the
  same database transaction (see `entrypoints/outbox.py`), and on the consumer side
  call `record_inbox(event.id, ...)` and check its return **before** applying any
  projection (see `entrypoints/events.py` in any service). Additive changes only
  within a version; a breaking change needs a new major event name.
- **New tenant-owned table** — add the `organization_id` column and, in the same
  migration, `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, `... FORCE ROW LEVEL
  SECURITY`, and a tenant-isolation policy comparing the column against
  `current_setting('app.current_organization_id')::uuid` (pattern in every
  `migrations/versions/0001_initial.py`). Never edit an applied migration — add a
  new one.
- **New agent runtime** — implement `AgentRuntime` from
  `runners/docker_runner/src/mvp_runner/application/ports.py` (`available`,
  `capabilities`, `execute`, `stream`, `cancel`), map provider events to
  `AgentEventKind`, and set `is_development_substitute` truthfully. Register it in
  `adapters/agent_registry.py` (`build_agents`, `SUPPORTED_RUNTIMES`) and add a
  matching entry to delivery's `domain/agent_runtimes.py::RUNTIME_COMPATIBILITY`.
  Do not branch the delivery workflow on the provider name — capability reporting
  and configuration validation are how differences should surface.
- **New model provider** (including an Anthropic-/OpenAI-compatible endpoint) — add
  one entry to `runners/docker_runner/src/mvp_runner/adapters/provider_catalog.py`
  (base URL, auth env var, egress hosts) plus one matching entry to delivery's
  `RUNTIME_COMPATIBILITY`. Never make the base URL tenant-configurable — that is an
  SSRF/secret-exfiltration vector, since the resolved credential is sent wherever
  the URL points.
- **New secret-bearing config** — it must be a `SecretReference`
  (`packages/python_common/src/mvp_common/contracts.py`), never a raw value, in any
  database row, event payload, or job payload. `SecretReference`'s own validators
  reject values containing `=` or `\n` specifically to catch someone passing a value
  where a reference was expected.

## Pitfalls observed in this codebase

- **Row-level security fails closed and silently.** Repository methods must call
  `set_config('app.current_organization_id', <org_id>, true)` on the session before
  querying (see any `adapters/postgres.py`). Forgetting it does not error — RLS
  simply returns zero rows, which looks like "not found" during debugging.
- **Temporal workflow code has determinism constraints.**
  `adapters/temporal_workflow.py` imports domain types inside
  `workflow.unsafe.imports_passed_through()`. Anything added to a `@workflow.run`
  method must stay deterministic (no direct I/O, no non-deterministic stdlib calls);
  side effects belong in `@activity.defn` functions in `adapters/activities.py`.
- **Runner job payloads are constructed in `_enqueue`**
  (`services/delivery/src/mvp_delivery/adapters/activities.py`). If you add a field
  here, confirm it is an identifier, a policy value, or a `SecretReference.model_dump()`
  — never a credential.
- **The model-credential `SecretResolver` runs only in the runner daemon, never
  inside the job container.** `adapters/leased_secret_resolver.py::LeasedSecretResolver`
  is instantiated and awaited exclusively by `entrypoints/daemon.py::run_job`,
  *before* the job container is launched; the resolved value is injected as a
  container environment variable via `DockerAgentExecutor.execute(environment=...)`.
  `entrypoints/job.py` (which runs inside the sandboxed container) never imports
  this resolver and never receives a `SecretReference` — only an already-resolved
  env var. Do not "simplify" this by moving resolution into an adapter that runs
  inside the container; that would hand credential-fetching capability to the
  sandboxed agent process, which ADR 0008/0009 deliberately avoid.
- **Three independent Alembic histories exist** (`control_plane`, `integrations`,
  `delivery`). `make migration-check` compiles all three from empty; a change to one
  service's migration does not need changes to the others, but forgetting to run the
  check for the one you touched is a common miss.
- **Workspace path handling is intentionally strict**
  (`runners/docker_runner/src/mvp_runner/adapters/workspace.py`): execution IDs are
  validated against a fixed lowercase-alphanumeric-plus-hyphen charset and the
  resolved path must satisfy `is_relative_to` the configured root. Do not relax this
  to support a convenience path format.
- **Runner and validator containers are configured with specific hardening flags**
  (`docker_agent.py`, `docker_validator.py`): `read_only=True`, `cap_drop=["ALL"]`,
  `no-new-privileges`, non-root UID, and explicit memory/CPU/PID limits. The
  validator container is always `network_disabled=True`, unconditionally. The job
  container is `network_disabled=True` too, **except** for the runtimes in
  `agent_registry.EGRESS_REQUIRED_RUNTIMES` (every runtime but `deterministic`),
  which instead join the `internal=True` egress network from
  `adapters/egress_network.py` when `AGENT_EGRESS_ENABLED=true` (see ADR 0009) —
  never pass both `network` and `network_disabled` to `containers.run` at once.
  `docker_agent.py`'s two `tmpfs` mounts differ: `/tmp` stays `noexec`, but
  `/home/app` (writable HOME for CLI-driven agents) is deliberately not, and
  requires explicit `uid=10001,gid=10001,mode=0700` mount options — verified
  empirically that a bare `rw` tmpfs mounts root-owned and unwritable by the
  non-root job user without them. Changes to these containers should preserve every
  flag unless the threat model is updated alongside the change
  (`docs/threat-model.md`).

## Reality check on defaults

The Compose stack's default configuration (`.env.example`) is
`GITHUB_ADAPTER=local`, `AGENT_ADAPTER=deterministic` (documentary only — actual
runtime selection is per-provider-configuration data, not this env var), and
`AGENT_EGRESS_ENABLED=false`. These are labeled development substitutes end to end
— in code (`is_development_substitute`), in the API responses, in the UI, and in
logs. The GitHub REST adapter, and the three real agent runtimes (`codex-cli`,
`claude-code-cli`, `claude-agent-sdk`), are packaged into the job image and are
code-complete, but a real execution still needs two things neither of which is on
by default: an organization-submitted model credential
(`POST /api/v1/organizations/{id}/model-credentials`) and
`AGENT_EGRESS_ENABLED=true` on the runner. A job that requests a real runtime
without both fails loudly (a normalized error result), never silently falling back
to `deterministic`. Do not describe any real adapter as production-ready in code
comments, commit messages, or documentation without first checking
[`docs/implemented-scope.md`](docs/implemented-scope.md) — and do not make
"add credentials" silently activate a real adapter or provider; that would violate
the non-negotiable principle in `AGENTS.md` against silent provider/model/auth
switching.
