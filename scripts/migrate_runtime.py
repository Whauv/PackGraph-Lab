from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.runtime_db import build_runtime_db


def main() -> dict:
    settings = get_settings()
    db = build_runtime_db(settings)
    payload = {
        "status": "ok",
        "runtime_db": db.health(),
    }
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
