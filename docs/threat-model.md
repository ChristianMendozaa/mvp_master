# Threat model

## Trust boundaries

Browser input, client requirements, repository data, webhook bodies, agent text, generated files, package scripts and preview responses are untrusted. OIDC, internal service identities, the event bus, the runner control channel, secret stores, Docker daemon and artifact store are separate trust boundaries.

## Implemented controls

- **Cross-tenant access:** server-side role checks, organization-scoped queries,
  service-owned databases, forced PostgreSQL RLS, tenant identities on events, and no
  frontend-only authorization decisions.
- **Prompt injection:** requirements are data, agents cannot approve work, runtime
  policy is outside the workspace, and agent success plus separately observed
  validation are both required.
- **Command injection:** runner validation uses executable/argument arrays without a
  shell; agent and validator containers are non-root, capability-free, and resource
  bounded. The validator container is always network-disabled; agent containers are
  network-disabled by default and, for the fixed set of runtimes that call a real
  model API, get network access restricted to one allowlisted provider host only
  (see "Model provider egress" below and ADR 0009) — never unrestricted egress.
- **Secret exfiltration:** persistent configuration and jobs contain secret references
  only; logging redacts sensitive key names; model/source-control credential values
  are absent from the local flow.
- **Model credential theft:** model API keys are encrypted in the same secret store
  as source-control credentials; job-bound capabilities to redeem one expire after
  60 seconds and are single-use; the resolved value is injected only as a job
  container environment variable by the runner daemon and is never present in
  `runner_jobs.payload`, the job's `exchange/input.json`, or a log line. The
  sandboxed agent process never resolves a `SecretReference` itself — see ADR 0009.
- **Model provider egress:** the allowlist of reachable hosts is compiled from a
  fixed, code-reviewed provider catalog, never from tenant-supplied input — a
  tenant-configurable base URL would be an SSRF / secret-exfiltration vector, since
  the resolved credential would follow it. The egress network is `internal=True` (no
  NAT rule exists for it at all — fail-closed, not a firewall rule that can be
  misconfigured open), and the only path out is a CONNECT proxy that neither
  terminates TLS nor accepts a destination outside the allowlist. Off by default
  (`AGENT_EGRESS_ENABLED=false`); a job requesting a real-agent runtime while egress
  is disabled fails loudly rather than running without network.
- **Webhook spoofing/replay:** constant-time HMAC verification, installation-based
  routing, unique delivery IDs, payload hashes, and duplicate acknowledgement.
- **Source credential theft:** manifest secrets are encrypted outside application
  data; job-bound capabilities expire after two minutes and are redeemed once;
  installation tokens are repository/purpose scoped and remain in runner memory.
- **Malicious Git configuration:** clean clone URLs, `GIT_ASKPASS`, disabled prompts,
  system config, hooks, LFS, and submodules, plus Git metadata outside the agent
  worktree.
- **Malicious workspaces:** execution IDs are validated, resolved paths must stay
  below a dedicated root, job containers receive only the workspace/exchange mounts,
  and verification receives a read-only workspace.
- **Unbounded execution:** per-execution attempts, turns, duration, and cost limits
  plus container CPU, memory, PID, and timeout controls.
- **Sensitive output:** structured JSON logs, centralized redaction, bounded event and
  evidence fields, and no chain-of-thought display.

## Controls still required

- Integration tests that prove RLS, webhook replay, and service identity denial.
- Safe clone and archive handling, symlink defenses across the whole checkout path,
  malicious Git configuration controls, and dependency-script policy.
- Production egress proxies and destination allowlists for control-plane *service*
  traffic. Agent-container egress is now policy-enforced (see "Model provider
  egress" above); other service-to-service and outbound control-plane egress is not.
- Organization/project budget rollups and immediate cancellation of a running
  container when workflow cancellation is signaled.
- Signed images, digest-pinned base images, SBOM generation, image scanning, and
  verified CI action provenance.
- Tenant-scoped artifact storage, retention policies, and log/trace access controls.
- The job/validator image's writable `/home/app` tmpfs is deliberately not
  `noexec` (some CLI/SDK-based agent runtimes extract and execute helper binaries
  from their cache directory there) — a larger surface than the fully `noexec`
  `/tmp` tmpfs. This deviation is scoped to that one mount and should be revisited
  if a narrower per-runtime allowlist of executable paths becomes practical.

## Residual risk

Development Docker-in-Docker requires a privileged daemon container and is not a production sandbox. Real agent runtimes remain disabled by default (`AGENT_EGRESS_ENABLED=false`) until a deployment explicitly enables scoped egress on isolated nodes with a hardened runtime.
