# Deployment guide

Only the Docker Compose development topology is implemented initially.

A production deployment must provide independently scalable service workloads, separate service database credentials, TLS, managed OIDC, a durable Temporal cluster, replicated JetStream, encrypted object storage, a secret-store adapter, private service networking, per-service identities, telemetry retention and backups.

Platform runners require dedicated nodes and a hardened isolation runtime such as rootless containerd with gVisor or Kata. The development Docker-in-Docker profile is not a supported production topology.

Rollouts use backward-compatible database expansion, compatible event/API versions, then data migration and later contract cleanup. Workflow code changes must pass Temporal replay tests before deployment.
