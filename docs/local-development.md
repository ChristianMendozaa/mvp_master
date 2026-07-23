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
migration and deterministic seed, and then starts the APIs, workers, runner, and web
application. `make migrate` and `make seed` are available for explicit maintenance;
they are not additional first-start steps.

`make down` preserves named volumes. `make clean-local` removes only this Compose project's generated containers and volumes after confirmation.

Useful local endpoints are Keycloak at `http://localhost:8081`, Temporal UI at
`http://localhost:8082`, Prometheus at `http://localhost:9090`, Jaeger at
`http://localhost:16686`, and MinIO Console at `http://localhost:9001`.

Before opening a change:

```bash
make verify
pnpm --filter @mvp-master/web build
```

## Real integrations

The default stack uses the simulated GitHub connector and deterministic agent. The
repository contains partial real adapters, but no Compose profile currently enables
them. Adding credentials does not activate them. See the integration guides for the
missing production wiring.
