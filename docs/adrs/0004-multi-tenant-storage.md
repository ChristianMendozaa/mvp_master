# ADR 0004: Tenant rows with PostgreSQL RLS

- Status: Accepted
- Date: 2026-07-23

## Decision

Each service uses its own database. Tenant-owned rows contain `organization_id`; application authorization is backed by PostgreSQL row-level security using transaction-local tenant context.

## Consequences

This supports many organizations without per-tenant migration overhead while providing defense in depth. High-assurance database-per-tenant deployments may be added behind storage adapters later.
