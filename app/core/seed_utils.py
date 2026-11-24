from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_seed_file(path: Path, default_data: Any) -> None:
    """Write *default_data* as JSON to *path* if the file does not already exist."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(default_data, handle, indent=2)
