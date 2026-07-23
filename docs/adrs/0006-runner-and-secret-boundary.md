# ADR 0006: Outbound runners and secret references

- Status: Accepted
- Date: 2026-07-23

## Decision

Runners enroll with a one-use credential, poll outbound for scoped jobs, and resolve secret references locally or through narrowly scoped credential leases. Jobs and events never carry ordinary secret values.

Local execution uses a dedicated Docker-in-Docker daemon rather than the host socket. Production requires a hardened isolated runtime.

## Consequences

Customer-hosted source and agent credentials can stay in customer infrastructure. Development setup has extra infrastructure and its privileged DinD daemon is explicitly not a production sandbox.
