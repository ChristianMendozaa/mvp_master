# ADR 0001: Monorepo and initial service boundaries

- Status: Accepted
- Date: 2026-07-23

## Decision

Use a monorepo with control-plane, integrations and delivery services plus an independently installable runner. Keep identity/audit as bounded modules in the control plane until independent scaling or ownership justifies extraction.

Each service owns a database and exposes versioned contracts. Shared packages contain contracts and universal primitives only.

## Consequences

The vertical slice proves real service boundaries without creating a service for every noun. Cross-context transactions use events and projections rather than shared tables.
