# GitHub App integration

## Boundary

`services/integrations` owns GitHub. Its application layer depends on the
provider-neutral `SourceControlProvider` port; `GitHubSourceControl` and
`LocalSourceControl` are adapters. Control-plane and delivery code exchange canonical
repository IDs and `ExternalReference` values, never Issue numbers as domain IDs.

The local adapter is the only assembled connector. It exposes a synthetic
installation, repository, Issue-like reference, and idempotent pull request so the
vertical slice exercises the real port without credentials.

## Implemented GitHub-facing code

- REST translations for listing installation repositories and opening pull requests.
- SHA-256 HMAC webhook signature validation using constant-time comparison.
- Installation-derived tenant routing, delivery-ID uniqueness, payload hashing, and
  duplicate acknowledgement.
- Database models for installation lifecycle, selected repositories, external
  references, webhook receipts, audit, and inbox processing.

Webhook secrets are read from a mounted file. The body-provided installation ID is
resolved through a server-owned routing table; an organization header is never
trusted.

## Production completion checklist

The real adapter must not be enabled until these pieces are added:

1. App manifest/installation and setup callback with signed state.
2. Private-key reference resolved by a secret-store adapter.
3. Short-lived installation-token minting in memory, with no token persistence or
   browser exposure.
4. Repository selection reconciliation and installation suspend, unsuspend,
   repository-change, and delete handlers.
5. Issue/comment ingestion, check-run publication, branch/commit/push operations,
   retry classification, and GitHub contract tests.
6. A reconciliation job for missed webhooks and rotated credentials.

The intended minimum repository permissions are metadata read, issues read/write,
contents read/write, pull requests read/write, and checks write. Each permission
must be revalidated against the exact enabled feature set before publishing the App.
