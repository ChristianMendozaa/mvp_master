# Testing strategy

Infrastructure-backed integrations tests use synthetic service credentials. Set
`INTEGRATIONS_TEST_DATABASE_URL` to a migrated integrations database using the
non-superuser integrations role before running `make test-integration`; without it,
the RLS test is reported as explicitly skipped rather than contacting an arbitrary
local database.

## Implemented gates

- Pure domain and in-memory application tests cover lifecycle invariants,
  permissions, budget checks, idempotent pull-request creation, webhook signatures,
  independent validation, and workspace path confinement.
- Contract checks validate all JSON Schemas and compare generated OpenAPI documents
  byte-for-byte with reviewed snapshots.
- Strict mypy, TypeScript, Ruff, ESLint, formatting, Next.js build, Compose-model
  validation, and Python/pnpm dependency audits run from repository commands.
- Vitest checks PKCE and same-origin helpers. An infrastructure-backed Playwright
  test drives structured intake, specification approval, work-item readiness,
  execution approval, isolated agent work, independent verification, and simulated
  pull-request delivery. Start the Compose stack, install Playwright's Chromium
  dependency once, and run `make test-e2e`.

## Required next tests

- Additional PostgreSQL RLS coverage for every tenant table plus outbox/inbox crash
  recovery.
- Temporal replay, worker-restart, retry, approval-signal, and cancellation tests.
- Runner attacks covering symlinks, malicious Git configuration, output redaction,
  container timeout, resource limits, and denied egress.
- Running the checked-in Compose/Playwright vertical slice as a required CI job.

All checked-in fixtures and identities are synthetic. Live provider certification is
opt-in and must never use production credentials in ordinary pull-request CI.
