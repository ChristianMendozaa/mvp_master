# GitHub App integration

## Boundary

`services/integrations` owns GitHub. Its application layer depends on the
provider-neutral `SourceControlProvider` port; `GitHubSourceControl` and
`LocalSourceControl` are adapters. Control-plane and delivery code exchange canonical
repository IDs and `ExternalReference` values, never Issue numbers as domain IDs.

Both the opt-in GitHub.com App adapter and the explicitly labeled local substitute
are assembled. The substitute exposes a synthetic installation, repository, and
idempotent pull request so deterministic tests exercise the port without credentials.

## Implemented GitHub-facing code

- A platform-operator-only App Manifest wizard at
  `/app/admin/integrations/github`. The local Keycloak owner carries the dedicated
  `mvp_master_platform_operator` OIDC claim; an organization role is not sufficient.
- The first-use wizard at `/app/onboarding` detects missing platform setup, sends an
  operator through the manifest flow, then resumes with organization installation
  and repository discovery. Non-operators receive a clear operator prerequisite.
- Backend-only manifest conversion. The returned private key, client secret, and
  webhook secret are encrypted with AES-256-GCM in a persistent volume; PostgreSQL
  stores `SecretReference` documents only. The master key is mounted separately.
- Tenant-bound, expiring, one-use setup state and GitHub user authorization before
  an installation can be associated with an organization.
- REST translations for paginated installation repositories, pull requests, and
  successful independent-verification check runs.
- SHA-256 HMAC webhook signature validation using constant-time comparison.
- Installation-derived tenant routing, delivery-ID uniqueness, payload hashing, and
  duplicate acknowledgement. Installation delete/suspend/unsuspend events update
  lifecycle state.
- A five-minute idempotent reconciliation worker marks removed repositories revoked.
- Short-lived job-bound source capabilities. Integrations exchanges each capability
  once for a repository-restricted installation token; GitHub tokens are never stored
  in jobs, databases, events, or agent containers.
- The runner performs credential-isolated HTTPS clone, commit, base-drift detection,
  bounded rebase/revalidation, and push. The agent and validator remain offline.

Webhook mode requires an externally reachable HTTPS `NEXT_PUBLIC_APP_URL`. Polling
mode is intended for localhost or private deployments. In both modes, the
body-provided installation ID is resolved through a server-owned routing table; an
organization header is never trusted.

## Deliberate v1 limits

- GitHub.com only; the provider model keeps web/API bases explicit for a future GHES
  adapter, but custom endpoints are not accepted by the v1 wizard.
- No PAT, OAuth App, deploy key, fork, submodule, LFS, issue/comment intake, merge,
  or workflow-file changes.
- Required App permissions are metadata read, contents write, pull requests write,
  and checks write. Runtime tokens are narrowed further per operation.
- Compose remains a local topology. Production still requires hardened runners,
  TLS, controlled egress, backups, and a managed OIDC/secret posture.
