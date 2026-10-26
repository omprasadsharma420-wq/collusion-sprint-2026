"""V5 world: identical v4 behavior, versioned export manifest only."""

import json
from pathlib import Path

from protocol_v5 import PROTOCOL_VERSION
from world_v4 import WorldV4


class WorldV5(WorldV4):
    def export(self, root: Path, *, source_commit: str | None = None) -> None:
        super().export(root, source_commit=source_commit)
        path = root / "trusted" / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["protocol_version"] = PROTOCOL_VERSION
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True,
                                   ensure_ascii=False) + "\n", encoding="utf-8")
