# Agent-provider integration

## Canonical selection

Delivery persists four separate choices: provider, agent runtime, model, and
authentication mode. A provider configuration cannot silently change any of them
during an execution. API-key mode requires a `SecretReference`; the database and job
payload never contain the secret value.

The runner-side `AgentRuntime` port covers availability, capabilities, execution,
normalized structured events, streaming, and cancellation. Domain and application
packages do not import provider SDKs.

## Implemented adapters

- `deterministic` is a development substitute used by Compose. It makes a bounded,
  predictable fixture change and emits normalized events.
- `codex-cli` translates a Codex JSON stream and supports local-session selection in
  code. It is not operational in the current image because the CLI, authenticated
  session mount, usage mapping, resume persistence, and runner secret resolver are
  intentionally absent.

There is no Anthropic adapter in this increment.

## Adding a provider

Add an adapter in the runner, map provider events to the canonical event types, and
advertise truthful capabilities. Add contract tests for cancellation, timeout,
structured output, usage, and failure normalization. Extend configuration
validation without branching the delivery workflow on vendor names.

Secret resolution belongs to the runner environment. Local sessions require an
explicit, read-only session mount; API keys require a scoped secret-store resolver.
Neither mode may fall back to the other. New outbound network destinations require a
threat-model and egress-policy update.
