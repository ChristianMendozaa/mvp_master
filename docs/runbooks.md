# Operational runbooks

## Stuck execution

1. Locate by execution and correlation ID.
2. Inspect the delivery state and Temporal history without exposing prompts or credentials.
3. Confirm runner lease/heartbeat and budget state.
4. Retry only activities classified as transient; otherwise request human intervention.
5. Never manually mark verification successful.

## Duplicate webhook or event

Confirm delivery/event ID in the inbox, compare payload hash, and inspect the prior processing outcome. Replaying a failed event must use the same idempotency identity.

## Runner loss

Revoke its active leases and credential, mark capacity unavailable, and let the durable workflow retry or await capacity according to policy. Cleanup is attempted on the runner and tracked as unresolved if the runner is unreachable.

## Suspected tenant breach

Disable affected identities and runners, revoke connector and secret leases, preserve append-only audit and trace evidence, stop affected workflows, identify impacted organization IDs, and follow the incident-response process before restoring access.
