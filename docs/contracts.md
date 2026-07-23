# API and event contracts

Public HTTP APIs are under `/api/v1`. Runner and service-only routes use
`/runner/v1` and `/internal/v1`. The GitHub webhook path is stable but authenticates
with the provider signature rather than OIDC. Reviewed OpenAPI snapshots live in
`packages/contracts/openapi`; live documents are served at
`/api/v1/openapi.json`.

Domain events use the shared envelope in
`packages/contracts/events/event-envelope.v1.schema.json`. Event names include their
major version, such as `membership.changed.v1` and `work_item.ready.v1`. The envelope
contains event, organization, correlation, causation, aggregate, timestamp, and
payload identifiers.

Producers write domain state and outbox rows in one database transaction. The outbox
publishes to JetStream with the event ID as the message deduplication identity.
Consumers store event IDs in an inbox before applying idempotent projections.
Delivery is therefore at least once, not exactly once.

Contract changes must be additive within `v1`. Removing or changing the meaning of a
field requires a new major contract. Generate API snapshots with:

```bash
uv run python scripts/export_openapi.py --write
make contract-check
```

The current checks detect stale snapshots and schema validity. Automated
consumer/provider compatibility and historical breaking-change detection are still
required.
