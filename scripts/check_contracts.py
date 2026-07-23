import json
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "packages" / "contracts"
    schemas = sorted(root.rglob("*.schema.json"))
    openapi_documents = sorted((root / "openapi").glob("*.openapi.json"))
    if not schemas:
        raise SystemExit("no contract schemas found")
    if not openapi_documents:
        raise SystemExit("no OpenAPI contracts found")
    for path in schemas:
        document = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(document)
    for path in openapi_documents:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not str(document.get("openapi", "")).startswith("3.1."):
            raise SystemExit(f"{path} is not an OpenAPI 3.1 contract")
        for route in document.get("paths", {}):
            if not (
                route.startswith("/api/v1/")
                or route.startswith("/internal/v1/")
                or route.startswith("/runner/v1/")
                or route.startswith("/health/")
                or route == "/webhooks/github"
            ):
                raise SystemExit(f"{path} exposes unversioned route: {route}")
    print(
        f"validated {len(schemas)} event schemas and "
        f"{len(openapi_documents)} OpenAPI contracts"
    )


if __name__ == "__main__":
    main()
