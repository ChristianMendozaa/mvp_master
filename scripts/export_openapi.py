import argparse
import json
from pathlib import Path
from typing import Any

from mvp_control_plane.entrypoints.api import app as control_plane_app
from mvp_delivery.entrypoints.api import app as delivery_app
from mvp_integrations.entrypoints.api import app as integrations_app

APPLICATIONS = {
    "control-plane.v1.openapi.json": control_plane_app,
    "delivery.v1.openapi.json": delivery_app,
    "integrations.v1.openapi.json": integrations_app,
}


def canonical(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or verify committed OpenAPI contracts")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    output_directory = (
        Path(__file__).resolve().parents[1] / "packages" / "contracts" / "openapi"
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    mismatches: list[str] = []
    for filename, app in APPLICATIONS.items():
        expected = canonical(app.openapi())
        path = output_directory / filename
        if arguments.write:
            path.write_text(expected, encoding="utf-8")
        elif not path.exists() or path.read_text(encoding="utf-8") != expected:
            mismatches.append(filename)

    if mismatches:
        names = ", ".join(mismatches)
        raise SystemExit(f"OpenAPI snapshots are stale: {names}; run scripts/export_openapi.py --write")
    action = "exported" if arguments.write else "verified"
    print(f"{action} {len(APPLICATIONS)} OpenAPI contracts")


if __name__ == "__main__":
    main()
