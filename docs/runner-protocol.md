# Runner protocol and security model

## Registration and job flow

An organization administrator creates a one-use enrollment token for a runner pool.
Only its hash is stored. The runner exchanges it for an ID and random credential;
only the credential hash remains in delivery storage.

Registered runners poll `/runner/v1/jobs/lease` over the control channel and complete
jobs through `/runner/v1/jobs/{job_id}/complete`. While a job is active, the runner
extends its lease through `/runner/v1/jobs/{job_id}/heartbeat`; abandoned leases are
eligible for reclamation after 45 seconds. A runner-side failure is reported as
structured, redacted evidence so the workflow can apply its bounded repair policy.
The current local protocol uses a bearer-style runner ID/credential pair. Jobs
contain work identifiers, selected runtime/model/authentication mode, a secret
reference, acceptance criteria, budgets, and structured validation commands. They
do not contain model or source-control credential values.

## Local isolation

Compose runs a dedicated privileged Docker-in-Docker daemon. The runner itself has no
host Docker socket. Each agent job has a dedicated copied checkout, non-root user,
read-only root filesystem, writable workspace only, disabled networking, dropped
capabilities, no-new-privileges, PID/CPU/memory limits, and a maximum duration.

Independent validation runs in a second container with the workspace mounted
read-only and networking disabled. Validation results are observed directly and are
required in addition to agent success. Workspaces and exchange files are removed in
a `finally` path.

## Known limits

- The local runner copies a fixture; it does not yet obtain a temporary repository
  lease, clone a selected repository, create a remote branch, or push a commit.
- Job leasing is polling-based and runner credentials are long-lived after
  enrollment. Rotation, revocation UI, per-lease fencing tokens, and control-channel
  mTLS are pending.
- Docker-in-Docker is a local-development convenience, not a hostile-code sandbox.
- Command allowlisting is represented by server-selected argument arrays but does
  not yet have an administrator-configurable policy engine.
- Artifact upload and durable cleanup reconciliation are pending.

Production runners require dedicated nodes, short-lived workload identity, hardened
isolation, deny-by-default egress with audited leases, encrypted local storage, and
remotely observable cleanup.
