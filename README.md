# MVP Master

MVP Master is a multi-tenant control plane for turning reviewed requirements into independently verified software changes through replaceable source-control and coding-agent adapters.

The repository is under active construction. See [Implemented scope](docs/implemented-scope.md) for an exact capability inventory, [Architecture](docs/architecture.md) for boundaries, [Delivery plan](docs/delivery-plan.md) for sequenced increments, and [Local development](docs/local-development.md) for setup.

## Repository map

- `apps/web` — Next.js product UI and browser-facing BFF
- `services/control_plane` — organizations, projects, intake, specifications, work items
- `services/integrations` — repository connections and provider adapters
- `services/delivery` — runners, execution workflow, verification, costs and artifacts
- `runners/docker_runner` — isolated execution worker
- `packages/contracts` — versioned HTTP and event contracts
- `docs` — architecture, security, operations and ADRs

## Common commands

```bash
make bootstrap
make up
make migrate
make seed
make verify
```

Never add credentials to `.env`. Local secrets belong in ignored files under `.secrets/`.
