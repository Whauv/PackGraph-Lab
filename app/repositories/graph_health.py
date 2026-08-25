from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def _safe_neo4j_uri(uri: str) -> str:
    parts = urlsplit(uri)
    if not parts.scheme or not parts.netloc:
        return uri
    host = parts.netloc.split("@")[-1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def graph_health(repo) -> dict[str, object]:
    return {
        "backend": "neo4j",
        "uri": _safe_neo4j_uri(repo.settings.neo4j_uri),
        "database": repo.settings.neo4j_database,
        "connected": False,
        "mode": "configured",
    }


def backend_status(repo) -> list[dict[str, object]]:
    return [
        {
            "backend": "neo4j",
            "active": True,
            "mode": "primary graph database",
            "status": "configured",
            "uri": _safe_neo4j_uri(repo.settings.neo4j_uri),
            "database": repo.settings.neo4j_database,
        },
    ]
