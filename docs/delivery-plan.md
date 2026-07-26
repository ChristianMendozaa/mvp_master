# Incremental delivery plan

Each increment must remain independently reviewable, preserve the provider-neutral
domain, update affected contracts and ADRs, and pass the repository definition of
done in `AGENTS.md`.

## 0. Architecture foundation — complete

Establish the monorepo, bounded contexts, hexagonal dependency rules, tenant-owned
databases, OIDC, versioned contracts, outbox/inbox messaging, Temporal, observability,
quality gates, Compose environment, threat model, and decision records.

Exit evidence: `make verify`, production web build, dependency audits, healthy local
services, and documented ownership.

## 1. Local complete vertical slice — complete

Prove organization and project selection, structured intake, immutable
specification approval, reviewed work-item readiness, explicit provider and budget
selection, durable approval, an isolated deterministic agent container, an
independent validator container, evidence capture, and a simulated GitHub pull
request through the real source-control port.

Exit evidence: the checked-in Playwright scenario completes from OIDC login to
`DELIVERED`, while the database records execution events, validation evidence,
costs, audit events, and an external reference.

## 2. Production GitHub delivery

Implemented for GitHub.com: deployment-owned App manifest registration, tenant
installation proof, encrypted secret references, installation-token leases,
repository reconciliation, real checkout, branch, commit/push, pull request and
check-run operations. Issue/comment synchronization and GHES remain later
increments.

Exit criteria: a repository selected during App installation completes the same
domain workflow without GitHub-specific types escaping the integrations context;
installation suspension, reduced access, and uninstallation revoke work safely.

## 3. Hardened agent and runner execution

Add enterprise secret-store adapters, fenced job leases, signed runner identity,
customer-hosted runner packaging, egress policy, hardened sandbox profiles, Codex
and Claude certification suites, detailed token/tool accounting, cancellation, and
Temporal replay/recovery coverage.

Exit criteria: provider/runtime/authentication combinations are explicit and
auditable, secrets stay within their trust boundary, duplicate leases cannot commit
twice, and hostile-repository tests demonstrate enforced limits.

## 4. Delivery evidence and collaboration

Add durable artifact storage, preview-provider ports and adapters, smoke and
end-to-end preview validation, notifications, richer client clarification,
approval delegation, and GitHub status/comment/check synchronization.

Exit criteria: every delivered change links immutable evidence and a preview or an
auditable reason no preview applies; notifications are idempotent and policy-bound.

## 5. Enterprise operations and scale

Add organization policy administration, SSO and lifecycle provisioning, retention
and export, regional deployment, disaster recovery, rate and quota controls,
support tooling, SLO dashboards, metering reconciliation, and certification for
additional source-control and work-management adapters.

Exit criteria: operational runbooks are exercised, tenant-isolation and recovery
tests run continuously, and each new integration passes shared port-contract suites
without changing workflow-domain rules.
