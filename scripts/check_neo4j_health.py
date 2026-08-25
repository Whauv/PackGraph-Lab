from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.repositories.graph_repository import GraphConnectionError, _safe_neo4j_uri, build_graph_repository


def main() -> dict:
    settings = get_settings()
    payload = {
        "backend": "neo4j",
        "uri": _safe_neo4j_uri(settings.neo4j_uri),
        "database": settings.neo4j_database,
        "connected": False,
        "status": "unavailable",
    }
    try:
        repository = build_graph_repository(settings)
    except GraphConnectionError as exc:
        payload["detail"] = str(exc)
    else:
        payload.update(repository.graph_health())
        close = getattr(repository, "close", None)
        if callable(close):
            close()
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
