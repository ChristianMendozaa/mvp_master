# ADR 0007: Versioned API and event contracts

- Status: Accepted
- Date: 2026-07-23

## Decision

HTTP APIs use `/api/v1` and committed OpenAPI snapshots. Events use CloudEvents-compatible envelopes with versioned JSON Schemas. Breaking changes require a new version and migration plan.

## Consequences

Services and the web client can evolve independently while CI detects accidental incompatibility.
