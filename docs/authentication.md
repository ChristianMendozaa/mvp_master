# Authentication and authorization

Keycloak is the local OIDC provider. The browser uses Authorization Code with PKCE through the Next.js BFF; tokens remain in secure HTTP-only cookies. Backend services validate issuer, audience, signature and expiry.

OIDC establishes identity only. The control-plane membership model is authoritative for organization roles and project/client grants. Other services consume versioned membership projections and deny requests when projection state is absent or stale beyond policy.

Roles:

- `OWNER`: organization settings, membership, connectors, budgets and all project actions.
- `ADMIN`: membership except ownership transfer, projects, connectors, provider and runner configuration.
- `DEVELOPER`: project intake/work-item work and approved execution requests.
- `REVIEWER`: specification, work-item, plan, budget and delivery approvals.
- `CLIENT`: create and view authorized intake, answer clarification, and approve assigned specification versions; no repository, execution internals, organization cost or audit access.

Implemented security-sensitive commands append the actor subject, organization,
action, target type/ID, and redacted details to the owning service's audit table.
Correlation, source IP, and user-agent fields are not yet populated consistently and
remain required before an internet-facing deployment.
