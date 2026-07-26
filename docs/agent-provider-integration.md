# Agent-provider integration

## Canonical selection

Delivery persists four separate choices: provider, agent runtime, model, and
authentication mode. A provider configuration cannot silently change any of them
during an execution — `services/delivery/.../domain/agent_runtimes.py::ensure_supported`
rejects any (runtime, provider, authentication_mode, is_development_substitute)
combination it does not explicitly know, at provider-configuration create time
(422), not after a runner round-trip. API-key mode requires a `SecretReference`;
the database and job payload never contain the secret value.

The runner-side `AgentRuntime` port covers availability, capabilities, execution,
normalized structured events, streaming, and cancellation. Domain and application
packages do not import provider SDKs — only `runners/docker_runner/src/mvp_runner/adapters/`
does.

## Implemented adapters

- `deterministic` — a development substitute used by Compose. Makes a bounded,
  predictable fixture change and emits normalized events. `is_development_substitute
  = True`, the only runtime for which that's true. Supports only `provider: "local"`,
  `authentication_mode: NONE`.
- `codex-cli` — shells the `codex` binary (`codex exec --json --sandbox
  workspace-write`). Supports both `LOCAL_SESSION` (a mounted ChatGPT OAuth session
  at `CODEX_HOME`) and `API_KEY_REFERENCE` (`OPENAI_API_KEY`, injected by the daemon
  — see "Model credentials" below) on the same binary. This is also the adapter that
  serves what a user might call "the Codex SDK": `@openai/codex-sdk` is a thin
  wrapper that spawns this exact same binary and speaks the same NDJSON protocol, so
  no separate Node-based adapter exists for it in this increment.
- `claude-code-cli` — shells the `claude` binary
  (`claude -p ... --output-format stream-json`). Supports `LOCAL_SESSION` (a mounted
  Claude Code OAuth session) and `API_KEY_REFERENCE`. `LOCAL_SESSION` is only valid
  with `provider: "anthropic"` — a subscription session cannot authenticate a
  third-party endpoint. `API_KEY_REFERENCE` also covers Anthropic-*compatible*
  providers served through the same CLI by pointing it at a different base URL —
  see "Provider catalog" below. `--bare` is used for `API_KEY_REFERENCE` runs (forces
  strict `ANTHROPIC_API_KEY`-only auth, skips hooks/CLAUDE.md/plugin discovery); never
  used for `LOCAL_SESSION`, which needs the mounted session read.
- `claude-agent-sdk` — the Python `claude-agent-sdk` package (`query()` /
  `ClaudeAgentOptions`). `API_KEY_REFERENCE` only, and only `provider: "anthropic"`.
  Anthropic's terms do not permit a third-party product to offer claude.ai
  subscription login through the Agent SDK, so `LOCAL_SESSION` is refused loudly
  rather than silently downgraded to the CLI adapter. The secret is passed via
  `ClaudeAgentOptions(env={"ANTHROPIC_API_KEY": ...})`, which the SDK merges over its
  own inherited environment when spawning its internal `claude` subprocess — this
  never touches the calling Python process's own `os.environ`.

All four are registered in `adapters/agent_registry.py::build_agents` — adding a
fifth means writing one adapter class, adding one dict entry there, and one entry in
delivery's `RUNTIME_COMPATIBILITY` table.

## Provider catalog (the scalability mechanism)

`adapters/provider_catalog.py` maps a `provider` identifier to how a runtime reaches
it: `auth_style` (which env var a resolved secret goes into),
`base_url` (`None` for a provider's own first-party API), and `egress_hosts` (for the
egress allowlist — see below). Current entries: `local` (no network),
`anthropic`, `openai`, and two Anthropic-compatible third-party vendors served
through `claude-code-cli` — `zhipu-glm` (`https://open.bigmodel.cn/api/anthropic`)
and `moonshot-kimi` (`https://api.moonshot.ai/anthropic`).

**Adding a new provider — including another Anthropic- or OpenAI-compatible
Chinese-model vendor — is one reviewed catalog entry, nothing else.** This is
deliberately not tenant-configurable: a tenant can never supply an arbitrary base
URL. Doing so would be an SSRF / secret-exfiltration vector, since the resolved
credential is sent to whatever host is configured. Delivery's
`domain/agent_runtimes.py::RUNTIME_COMPATIBILITY` needs a matching entry (which
runtimes may pair with the new provider, and under which authentication modes).

## Model credentials

Resolving a model API key mirrors the existing Git source-credential flow exactly
(ADR 0008), on a distinct JWT audience: delivery mints a 60-second, single-use,
job-scoped capability (`POST /runner/v1/jobs/{job_id}/model-capability`); the
runner's **daemon** (never the sandboxed agent process) redeems it once against
integrations (`POST /internal/v1/model-credentials/exchange`, audience
`mvp-integrations-model`), which validates the capability, confirms the referenced
secret belongs to the requesting organization, and returns the plaintext value
exactly once. The daemon injects that value directly into the job container's
environment at launch (see `adapters/leased_secret_resolver.py` and
`entrypoints/daemon.py::run_job`). The container never receives a
`SecretReference` and never resolves one itself.

An organization submits the underlying API key value once, out of band, via
`POST /api/v1/organizations/{organization_id}/model-credentials` (integrations),
which writes it to the encrypted secret store under a
`model-credentials/{organization_id}` namespace and returns only the resulting
`SecretReference` identifiers.

## Model provider egress

Real-agent job containers (every runtime except `deterministic`) get network access
restricted to exactly the resolved provider host, via a fail-closed `internal=True`
Docker network plus a CONNECT proxy (see ADR 0009 and `adapters/egress_network.py`).
Off by default (`AGENT_EGRESS_ENABLED=false`); a job requesting a real-agent runtime
while egress is disabled fails loudly with a normalized error rather than running
without network. The validator container is never touched by any of this.

## `LOCAL_SESSION` operator flow

`LOCAL_SESSION` is intended for `CUSTOMER_HOSTED` runner pools (the
`RunnerPoolCreate.runner_type` enum already supports this): the customer runs
`claude /login` or `codex login` once on their own runner host, and the resulting
OAuth session directory is mounted read-only into the job container
(`Settings.claude_session_path` / `codex_session_path`). The adapter copies it into
the container's writable `HOME` at start (`ClaudeCodeCliAgent._prepare_local_session`;
`CodexCliAgent` expects an analogous mounted+copied `CODEX_HOME`) rather than pointing
the CLI directly at the read-only mount, since both CLIs need a writable session
directory to run in.

## `stream()` and `cancel()` semantics

`stream()` on every adapter is a post-execution replay of the normalized event list,
not a live stream — the job container is a batch process whose only output channel
is `exchange/output.json`; live streaming to delivery would require the sandboxed
container to reach delivery's HTTP API, which the isolation model forbids. `cancel()`
is best-effort process termination (terminate → 5s → kill), exercised by unit tests
but not yet wired to workflow-level cancellation — see `docs/threat-model.md`
"Controls still required".

## Adding a provider or runtime — checklist

- Runner: write one `AgentRuntime` adapter (`available`, `capabilities`, `execute`,
  `stream`, `cancel`); map the provider/CLI's events to the canonical
  `AgentEventKind`s; advertise truthful capabilities (`is_development_substitute`,
  `supported_authentication_modes`); add it to `agent_registry.build_agents` and
  `SUPPORTED_RUNTIMES`.
- Runner: add one `provider_catalog.py` entry if the provider is new.
- Delivery: add one `RUNTIME_COMPATIBILITY` entry (`domain/agent_runtimes.py`) naming
  the allowed providers and authentication modes.
- Never branch the delivery workflow on the provider or runtime name — capability
  reporting and this validation table are how differences surface.
- New outbound network destinations require a threat-model update and an entry in
  the provider catalog's `egress_hosts` (see ADR 0009) — never tenant input.
- Add adapter tests using a fake executable / monkeypatched SDK call (no live
  credentials or network — AGENTS.md).
