import json
from pathlib import Path

document = json.loads(Path("src/status.json").read_text(encoding="utf-8"))
assert document["status"] == "Delivered by deterministic local agent"
