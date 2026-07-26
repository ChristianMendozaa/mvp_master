# ADR 0006: Outbound runners and secret references

- Status: Accepted
- Date: 2026-07-23

## Decision

Runners enroll with a one-use credential, poll outbound for scoped jobs, and resolve secret references locally or through narrowly scoped credential leases. Jobs and events never carry ordinary secret values.

Local execution uses a dedicated Docker-in-Docker daemon rather than the host socket. Production requires a hardened isolated runtime.

## Consequences

Customer-hosted source and agent credentials can stay in customer infrastructure. Development setup has extra infrastructure and its privileged DinD daemon is explicitly not a production sandbox.

## Amendment (2026-07-26)

Model-provider API keys now use the exact "narrowly scoped credential lease"
mechanism this ADR anticipated: a short-lived, single-use, job-scoped capability
minted by delivery and redeemed once by the runner daemon against integrations'
secret store, with the resolved value injected only as a job-container environment
variable. See ADR 0009 for the full mechanism and for the accompanying change to
job-container network access (real agent runtimes now get network access scoped to
exactly one allowlisted provider host, via a fail-closed internal Docker network and
proxy — `deterministic` and the validator container are unaffected).
