# ADR 0003: Temporal workflows and JetStream events

- Status: Accepted
- Date: 2026-07-23

## Decision

Use Temporal for long-running delivery orchestration and NATS JetStream for versioned cross-context domain events. Publish events through transactional outboxes and consume them with transactional inbox deduplication.

## Consequences

Retries, approval waits, cancellation and resumability are explicit. Event delivery remains at-least-once; handlers must be idempotent and no exactly-once claim is made.
