from __future__ import annotations

import re
from typing import Any


class EntityResolutionAgent:
    def analyze(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            label = str(
                row.get("name")
                or row.get("title")
                or row.get("label")
                or row.get("entity_id")
                or row.get("material_id")
                or row.get("supplier_id")
                or row.get("preview")
                or ""
            ).strip()
            if not label:
                continue
            normalized = re.sub(r"[^a-z0-9]+", "", label.casefold())
            groups.setdefault(normalized, []).append({"label": label, "row": row})

        duplicate_groups = []
        for normalized, matches in groups.items():
            distinct_labels = list(dict.fromkeys(item["label"] for item in matches))
            if len(distinct_labels) > 1:
                duplicate_groups.append(
                    {
                        "canonical_key": normalized,
                        "labels": distinct_labels,
                        "count": len(matches),
                        "review_before_merge": True,
                    }
                )

        return {
            "checked_rows": len(rows),
            "duplicate_groups": duplicate_groups,
            "review_before_merge": bool(duplicate_groups),
        }
