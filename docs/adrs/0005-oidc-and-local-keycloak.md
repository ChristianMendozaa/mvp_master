# ADR 0005: OIDC and local Keycloak

- Status: Accepted
- Date: 2026-07-23

## Decision

Use OIDC for user identity and Keycloak for the local stack. Keep membership roles and project/client grants in the canonical authorization model.

## Consequences

Enterprise identity providers can replace Keycloak without changing authorization rules. Keycloak development mode and realm import are local-only.
