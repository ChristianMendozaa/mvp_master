# ADR 0009: Scoped model-provider egress and the model-credential lease

- Status: Accepted
- Date: 2026-07-26

## Context

Real coding-agent runtimes (`claude-agent-sdk`, `claude-code-cli`, `codex-cli`) must
call a real model provider's API over the network. Every job container has run with
`network_disabled=True` since ADR 0006 — correct for the `deterministic` substitute,
which touches nothing external, but incompatible with any runtime that actually
calls a model. ADR 0008 established the equivalent problem for Git credentials
("coding agents receive neither network access nor source credentials") and solved
it by keeping trusted transport (git push/pull, credential exchange) entirely
outside the agent process, in the runner daemon. Model-provider access needs the
same shape, but the agent process itself is the thing that must reach the network —
it cannot be proxied around the way Git transport was.

## Decision

Job containers stay network-denied by default. A named, fixed set of runtimes —
every runtime except `deterministic` (`agent_registry.EGRESS_REQUIRED_RUNTIMES`) —
gets network access restricted to exactly the resolved provider host, never
unrestricted egress:

- The runner creates a dedicated Docker network (`mvp-agent-egress` by default) with
  `internal=True`. Docker installs no NAT/masquerade rule for an `internal` network,
  so a container attached to it alone has no route off the host at all — this is a
  fail-closed property, not a firewall rule that can be misconfigured into
  fail-open.
- A single long-lived CONNECT-proxy container (tinyproxy) is attached to both that
  internal network and the default bridge (which has normal outbound routing). It is
  the only path out. Its allowlist (`Filter` + `FilterDefaultDeny Yes`) is generated
  from `adapters/provider_catalog.py::allowlisted_hosts()` — a fixed, reviewed list
  compiled from code, never from tenant input. A tenant-supplied base URL is never
  accepted anywhere in this system (see `docs/agent-provider-integration.md`) — this
  is what makes the allowlist meaningful rather than a rubber stamp.
- The proxy does **not** terminate TLS. It only allows or denies the `CONNECT`
  method to specific hostnames on port 443 (`ConnectPort 443`); provider traffic
  stays end-to-end encrypted between the agent process and the real provider.
- Real-agent job containers get `HTTPS_PROXY`/`https_proxy`/`HTTP_PROXY`/
  `http_proxy` set (both casings — empirically, not every CLI honors the same
  convention) and join the internal network instead of running
  `network_disabled=True`.
- `AGENT_EGRESS_ENABLED` defaults to `false`. A job that requests a real-agent
  runtime while egress is disabled fails loudly (a normalized error result), never
  silently running without network. Enabling egress in a deployment is an explicit,
  reviewed operator decision, matching the `AGENT_ADAPTER=deterministic` /
  `GITHUB_ADAPTER=local` default-off pattern already established for other real
  integrations.
- The validator container is **never** touched by any of this — it remains
  unconditionally `network_disabled=True`, exactly as ADR 0006 established.

### The model-credential lease

Resolving a model API key follows the exact shape ADR 0008 established for Git
credentials: delivery mints a short-lived (60s), single-use, job-scoped capability
(`POST /runner/v1/jobs/{job_id}/model-capability`, JWT audience
`mvp-integrations-model` — distinct from `mvp-integrations-source` so the two
capability kinds are never interchangeable); the runner's daemon (never the
sandboxed agent process) redeems it once against integrations
(`POST /internal/v1/model-credentials/exchange`), which validates the capability,
confirms the referenced secret belongs to the requesting organization, and returns
the plaintext value exactly once. The daemon injects that value directly into the
job container's environment at launch. The container never receives a
`SecretReference`, never resolves one itself, and the value never touches
`runner_jobs.payload`, `exchange/input.json`, or a log line.

Organizations submit the underlying API key value once, out of band, via
`POST /api/v1/organizations/{organization_id}/model-credentials` (integrations),
which writes it to the existing encrypted secret store under a
`model-credentials/{organization_id}` namespace and returns only the resulting
`SecretReference` identifiers — never the value.

## Consequences

Enabling a real agent runtime for a deployment now requires two things instead of
one: an organization must submit a real API key (or, for `LOCAL_SESSION`, a runner
operator must mount a real OAuth session), *and* the runner must have
`AGENT_EGRESS_ENABLED=true` with a proxy image available. Both are off by default.
Adding a new model provider (including a Chinese-model vendor served through an
Anthropic-compatible endpoint) means adding one entry to
`adapters/provider_catalog.py` and one entry to
`services/delivery/.../domain/agent_runtimes.py` — nothing about the egress or
credential-lease mechanism changes.

The runner process now depends on being able to create Docker networks and run a
long-lived proxy container inside its Docker-in-Docker daemon; `docs/threat-model.md`
is updated accordingly. The job/validator image gains a writable, non-`noexec`
`/home/app` tmpfs (needed by the CLI/SDK-based runtimes for config and cache) — a
documented, narrow deviation from the otherwise-`noexec` tmpfs policy.
