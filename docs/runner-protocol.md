# Runner protocol and security model

## Registration and job flow

An organization administrator creates a one-use enrollment token for a runner pool.
Only its hash is stored. The runner exchanges it for an ID and random credential;
only the credential hash remains in delivery storage.

Registered runners poll `/runner/v1/jobs/lease` over the control channel and complete
jobs through `/runner/v1/jobs/{job_id}/complete`. While a job is active, the runner
extends its lease through `/runner/v1/jobs/{job_id}/heartbeat`; abandoned leases are
eligible for reclamation after 45 seconds. A runner-side failure is reported as
structured, redacted evidence so the workflow can apply its bounded repair policy.
The current local protocol uses a bearer-style runner ID/credential pair. Jobs
contain work identifiers, selected provider/runtime/model/authentication mode, a
secret reference, acceptance criteria, budgets, and structured validation commands.
They do not contain model or source-control credential values.

When no delivery job is available, the runner also polls
`/runner/v1/provider-verifications/lease`. A verification is tenant- and pool-bound,
uses the same heartbeat and runner identity rules, and may redeem only a model
credential capability. It has no source capability, repository, publish permission,
validator phase, or durable workspace. Completion records a sanitized result and
usage counts for onboarding.

For a connected repository, an actively leased runner requests a two-minute,
purpose-bound source capability from delivery. Integrations accepts the signed
capability once and mints a GitHub installation token restricted to the selected
repository and either checkout-read or publish-write. The runner uses `GIT_ASKPASS`
without embedding the token in a URL or argument. Git metadata remains outside the
agent-mounted worktree.

For a job whose `authentication_mode` is `API_KEY_REFERENCE`, the same actively
leased runner requests a 60-second, single-use **model capability** from delivery
(`POST /runner/v1/jobs/{job_id}/model-capability`) — a distinct JWT audience from the
source capability above, so the two are never interchangeable. The runner's daemon
(never the agent process inside the job container) redeems it once against
integrations (`POST /internal/v1/model-credentials/exchange`), which confirms the
referenced secret belongs to the requesting organization and returns the plaintext
value exactly once. The daemon injects that value directly into the job container's
environment at launch; it is never written to the job payload, `exchange/input.json`,
or a log line. See `docs/agent-provider-integration.md` for the full flow and
`docs/adrs/0009-scoped-model-provider-egress.md` for the design rationale.

## Local isolation

Compose runs a dedicated privileged Docker-in-Docker daemon. The runner itself has no
host Docker socket. Each agent job has a dedicated copied checkout, non-root user,
read-only root filesystem, writable workspace only, dropped capabilities,
no-new-privileges, PID/CPU/memory limits, and a maximum duration. Networking is
disabled by default (`deterministic`, always); for the runtimes that call a real
model API, networking is instead restricted to exactly the resolved provider host
via a fail-closed internal Docker network and CONNECT proxy, gated behind
`AGENT_EGRESS_ENABLED` (off by default).

Independent validation runs in a second container with the workspace mounted
read-only and networking disabled. Validation results are observed directly and are
required in addition to agent success. Workspaces and exchange files are removed in
a `finally` path.

## Known limits

- The simulated connector still copies a fixture. Real GitHub installations use a
  temporary source capability, clone, deterministic execution branch, revalidation
  after base drift, and push.
- Job leasing is polling-based and runner credentials are long-lived after
  enrollment. Rotation, revocation UI, per-lease fencing tokens, and control-channel
  mTLS are pending.
- Docker-in-Docker is a local-development convenience, not a hostile-code sandbox.
- Command allowlisting is represented by server-selected argument arrays but does
  not yet have an administrator-configurable policy engine.
- Artifact upload and durable cleanup reconciliation are pending.

Production runners require dedicated nodes, short-lived workload identity, hardened
isolation, deny-by-default egress with audited leases, encrypted local storage, and
remotely observable cleanup.
