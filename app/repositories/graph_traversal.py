from __future__ import annotations

from collections import defaultdict
from typing import Any


def relationship_preview(repo, material_id: str | None = None) -> list[dict[str, Any]]:
    links = repo.relationships
    if material_id:
        links = [rel for rel in links if rel["from"] == material_id or rel["to"] == material_id]
    return links[:80]


def graph_subgraph(repo, material_id: str) -> dict[str, Any]:
    material = repo.material_index.get(material_id)
    if not material:
        return {"nodes": [], "edges": []}
    nodes: dict[str, dict[str, Any]] = {
        material_id: {"id": material_id, "label": material["name"], "type": "material"},
    }
    edges = []
    for relationship in repo.relationship_preview(material_id):
        source = relationship["from"]
        target = relationship["to"]
        edges.append({"source": source, "target": target, "type": relationship["type"]})
        if source not in nodes:
            nodes[source] = repo._node_descriptor(source)
        if target not in nodes:
            nodes[target] = repo._node_descriptor(target)
    return {"nodes": list(nodes.values()), "edges": edges}


def graph_path(repo, source_id: str, target_id: str) -> dict[str, Any]:
    queue = [(source_id, [source_id])]
    seen = {source_id}
    while queue:
        current, path = queue.pop(0)
        if current == target_id:
            nodes = [repo._node_descriptor(node_id) for node_id in path]
            edges = []
            for index in range(len(path) - 1):
                edge = repo._relationship_between(path[index], path[index + 1])
                if edge:
                    edges.append({"source": edge["from"], "target": edge["to"], "type": edge["type"]})
            return {"path": nodes, "edges": edges}
        for relationship in repo.relationships_by_node.get(current, []):
            neighbor = relationship["to"] if relationship["from"] == current else relationship["from"]
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return {"path": [], "edges": []}


def graph_node_insight(repo, node_id: str) -> dict[str, Any]:
    node = repo._node_descriptor(node_id)
    relationships = repo.relationships_by_node.get(node_id, [])
    relationship_counts = defaultdict(int)
    related = []
    seen_related = set()
    for relationship in relationships:
        relationship_counts[relationship["type"]] += 1
        other_id = relationship["to"] if relationship["from"] == node_id else relationship["from"]
        if other_id in seen_related:
            continue
        seen_related.add(other_id)
        related_node = repo._node_descriptor(other_id)
        related.append(
            {
                "id": related_node["id"],
                "label": related_node["label"],
                "type": related_node["type"],
                "relationship": relationship["type"],
            }
        )
    return {
        "node": node,
        "summary": f"{node['label']} is connected to {len(related)} nearby nodes across {len(relationship_counts)} relationship types.",
        "metrics": [],
        "facts": [],
        "relationship_counts": [
            {"label": item_type.replace("_", " ").title(), "value": count}
            for item_type, count in sorted(relationship_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "timeline": [],
        "related": related[:12],
    }
