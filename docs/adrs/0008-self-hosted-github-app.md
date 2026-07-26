# ADR 0008: Deployment-owned GitHub App and scoped source capabilities

- Status: Accepted
- Date: 2026-07-25

## Decision

Each self-hosted deployment may register one opt-in GitHub.com App through a
platform-operator-only manifest flow. App credentials are written directly to an
encrypted secret adapter and application data stores references only. Tenant owners
install the configured App using expiring one-use state and a GitHub user
authorization check.

Delivery never handles a GitHub token. An actively leased runner obtains a
short-lived signed capability; integrations redeems it once and mints a
repository- and purpose-restricted installation token. The runner performs trusted
Git transport outside the offline agent and validator containers.

Webhook delivery is optional for private/local deployments. Idempotent polling
reconciliation remains enabled so access removal converges without a public inbound
endpoint.

## Consequences

The deployment operator owns credential rotation and must preserve the secret master
key independently of encrypted data. GitHub.com works without a central MVP Master
service, while GitHub Enterprise Server remains a future adapter/configuration
variant. Runners require controlled GitHub egress, but coding agents receive neither
network access nor source credentials.
