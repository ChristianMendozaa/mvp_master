# Local development

## Prerequisites

- Docker Engine with Compose v2 and access to the daemon
- GNU Make

The stack is containerized; host Node and Python are optional. Do not place a sudo password in shell commands, `.env`, Make targets, or repository files. Configure Docker access using an operating-system-supported interactive process.

## Setup

```bash
cp .env.example .env
make bootstrap
make up
```

Open the web application at `http://localhost:3000`. The checked-in Keycloak realm contains synthetic local-only users documented in `.env.example`.

`make up` builds the images, waits for infrastructure, runs every service-owned
migration and the minimal local bootstrap, and then starts the APIs, workers, runner,
and web application. The bootstrap creates only the `Local Workspace`, owner
membership, runner pool, and runner identity. It does not create a project,
repository connection, or provider configuration.

Use `make up-guided` for real-agent onboarding. This explicitly enables the
provider-host allowlisted egress proxy; the validator and deterministic agent remain
offline. `make migrate` and `make seed` remain available for explicit maintenance.

`make down` preserves named volumes. `make clean-local` removes only this Compose
project's generated containers and all named volumes after confirmation, including
PostgreSQL, NATS, MinIO, runner workspaces, and encrypted integration secrets. It is
an irreversible factory reset.

Useful local endpoints are Keycloak at `http://localhost:8081`, Temporal UI at
`http://localhost:8082`, Prometheus at `http://localhost:9090`, Jaeger at
`http://localhost:16686`, and MinIO Console at `http://localhost:9001`.

Before opening a change:

```bash
make verify
pnpm --filter @mvp-master/web build
```

## Real integrations

The default stack starts without a repository or agent configuration. Sign in as the
local owner and follow `http://localhost:3000/app/onboarding`; it links the platform
operator through GitHub App registration when needed, then continues with tenant
installation, repository discovery, API-key storage, and agent verification. Choose
polling for localhost.

Compose generates a local master key in the `integrations-secrets` volume and uses it
to encrypt manifest credentials. Removing that volume destroys the local ability to
decrypt those credentials; revoke the corresponding GitHub App keys as part of
recovery. Webhook mode requires setting `NEXT_PUBLIC_APP_URL` to an externally
reachable HTTPS origin before registration.

GitHub and real agents are opt-in and never replace their labeled development
substitutes silently.
