# ADR 0002: Hexagonal Architecture

- Status: Accepted
- Date: 2026-07-23

## Decision

All backend deployables use domain, application, adapter and entrypoint layers with dependencies pointing inward. External providers, persistence, messaging, orchestration and Docker are explicit ports.

## Consequences

Provider and infrastructure replacements do not rewrite business workflows. More translation code is accepted in exchange for testability and stable domain boundaries.
