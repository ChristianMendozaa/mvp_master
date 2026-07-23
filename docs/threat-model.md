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
  shell; agent and validator containers are non-root, capability-free, resource
  bounded, and network-disabled.
- **Secret exfiltration:** persistent configuration and jobs contain secret references
  only; logging redacts sensitive key names; model/source-control credential values
  are absent from the local flow.
- **Webhook spoofing/replay:** constant-time HMAC verification, installation-based
  routing, unique delivery IDs, payload hashes, and duplicate acknowledgement.
- **Malicious workspaces:** execution IDs are validated, resolved paths must stay
  below a dedicated root, job containers receive only the workspace/exchange mounts,
  and verification receives a read-only workspace.
- **Unbounded execution:** per-execution attempts, turns, duration, and cost limits
  plus container CPU, memory, PID, and timeout controls.
- **Sensitive output:** structured JSON logs, centralized redaction, bounded event and
  evidence fields, and no chain-of-thought display.

## Controls still required

- Integration tests that prove RLS, webhook replay, and service identity denial.
- A secret-store resolver and short-lived source/model credential leases.
- Safe clone and archive handling, symlink defenses across the whole checkout path,
  malicious Git configuration controls, and dependency-script policy.
- Production egress proxies and destination allowlists. Local agent/validator
  networking is disabled, but control-plane service egress is not policy-enforced.
- Organization/project budget rollups and immediate cancellation of a running
  container when workflow cancellation is signaled.
- Signed images, digest-pinned base images, SBOM generation, image scanning, and
  verified CI action provenance.
- Tenant-scoped artifact storage, retention policies, and log/trace access controls.

## Residual risk

Development Docker-in-Docker requires a privileged daemon container and is not a production sandbox. Real agent runtimes remain disabled by default until deployed on isolated nodes with a hardened runtime and controlled egress.
