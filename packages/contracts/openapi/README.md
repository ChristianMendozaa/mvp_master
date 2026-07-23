# OpenAPI contracts

The JSON files in this directory are canonical, generated snapshots of the three
backend APIs. Change an API deliberately, run
`uv run python scripts/export_openapi.py --write`, review the semantic diff, and
retain backward compatibility within `v1`.

The live service documents remain available at `/api/v1/openapi.json`.
