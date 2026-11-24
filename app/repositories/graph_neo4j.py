from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any

from app.core.config import get_settings
from app.repositories.graph_repository import (
    GraphConnectionError,
    GraphQueryFailure,
    LocalGraphRepository,
    _safe_neo4j_uri,
)


class Neo4jAdminRepository:
    def __init__(self, uri: str, username: str, password: str):
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def run(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def close(self) -> None:
        self.driver.close()


class Neo4jGraphRepository(LocalGraphRepository):
    ID_KEYS = [
        "material_id",
        "supplier_id",
        "application_id",
        "regulation_id",
        "document_id",
        "stream_id",
        "report_id",
        "snapshot_id",
        "region_id",
        "industry_id",
        "certification_id",
    ]

    LABEL_TO_ID_KEY = {
        "Material": "material_id",
        "Supplier": "supplier_id",
        "Application": "application_id",
        "Regulation": "regulation_id",
        "SourceDocument": "document_id",
        "RecyclingStream": "stream_id",
        "TestReport": "report_id",
        "QuarterlySnapshot": "snapshot_id",
        "Region": "region_id",
        "Industry": "industry_id",
        "Certification": "certification_id",
    }

    LABEL_TO_TYPE = {
        "Material": "material",
        "Supplier": "supplier",
        "Application": "application",
        "Regulation": "regulation",
        "SourceDocument": "document",
        "RecyclingStream": "recycling_stream",
        "TestReport": "test_report",
        "QuarterlySnapshot": "snapshot",
        "Region": "region",
        "Industry": "industry",
        "Certification": "certification",
    }

    CONSTRAINTS = [
        "CREATE CONSTRAINT material_id IF NOT EXISTS FOR (m:Material) REQUIRE m.material_id IS UNIQUE",
        "CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.supplier_id IS UNIQUE",
        "CREATE CONSTRAINT application_id IF NOT EXISTS FOR (a:Application) REQUIRE a.application_id IS UNIQUE",
        "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.regulation_id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.document_id IS UNIQUE",
    ]

    def __init__(self, settings=None) -> None:
        super().__init__()
        self.settings = settings or get_settings()
        self.driver = None
        self.connection_state = "configured"
        self.audit_path = self.settings.packgraph_runtime_dir / "neo4j_query_audit.jsonl"
        if not self.settings.neo4j_test_stub:
            from neo4j import GraphDatabase

            try:
                self.driver = GraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                )
                self.driver.verify_connectivity()
                self.connection_state = "connected"
            except Exception as exc:
                self.connection_state = "unavailable"
                raise GraphConnectionError(
                    f"Neo4j is unavailable at {_safe_neo4j_uri(self.settings.neo4j_uri)} for database {self.settings.neo4j_database}."
                ) from exc
        else:
            self.connection_state = "stubbed"
        if self.settings.neo4j_auto_ingest:
            self.sync_bundle_to_neo4j()

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def sync_bundle_to_neo4j(self) -> None:
        if not self.driver:
            raise GraphConnectionError("Neo4j sync requires a live Neo4j connection.")
        entity_map = {
            "materials": ("Material", "material_id"),
            "suppliers": ("Supplier", "supplier_id"),
            "applications": ("Application", "application_id"),
            "regulations": ("Regulation", "regulation_id"),
            "certifications": ("Certification", "certification_id"),
            "recycling_streams": ("RecyclingStream", "stream_id"),
            "regions": ("Region", "region_id"),
            "industries": ("Industry", "industry_id"),
            "source_documents": ("SourceDocument", "document_id"),
            "test_reports": ("TestReport", "report_id"),
            "quarterly_snapshots": ("QuarterlySnapshot", "snapshot_id"),
        }
        relation_queries = {
            "TARGETS_APPLICATION": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Application {application_id: row.to})
                MERGE (a)-[:TARGETS_APPLICATION]->(b)
            """,
            "SUPPLIED_BY": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Supplier {supplier_id: row.to})
                MERGE (a)-[:SUPPLIED_BY]->(b)
            """,
            "HAS_DOCUMENT": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:SourceDocument {document_id: row.to})
                MERGE (a)-[:HAS_DOCUMENT]->(b)
            """,
            "SUBSTITUTES_WITH": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Material {material_id: row.to})
                MERGE (a)-[:SUBSTITUTES_WITH]->(b)
            """,
            "RECYCLES_INTO": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:RecyclingStream {stream_id: row.to})
                MERGE (a)-[:RECYCLES_INTO]->(b)
            """,
            "REVIEWED_UNDER": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Regulation {regulation_id: row.to})
                MERGE (a)-[:REVIEWED_UNDER]->(b)
            """,
            "SUPPLIES": """
                UNWIND $rows AS row
                MATCH (a:Supplier {supplier_id: row.from})
                MATCH (b:Material {material_id: row.to})
                MERGE (a)-[:SUPPLIES]->(b)
            """,
        }
        with self.driver.session(database=self.settings.neo4j_database) as session:
            for query in self.CONSTRAINTS:
                session.run(query).consume()
            for key, (label, id_key) in entity_map.items():
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:{label} {{{id_key}: row.{id_key}}})
                    SET n += row
                    """,
                    {"rows": [self._normalize_neo4j_properties(row) for row in self.bundle[key]]},
                ).consume()
            for rel_type, query in relation_queries.items():
                rows = [rel for rel in self.relationships if rel["type"] == rel_type]
                session.run(query, {"rows": rows}).consume()

    def ingest_uploaded_artifact(self, record: dict[str, Any], kind: str) -> None:
        if not self.driver:
            raise GraphConnectionError("Uploaded artifact ingest requires a live Neo4j connection.")
        with self.driver.session(database=self.settings.neo4j_database) as session:
            if kind == "test_report":
                session.run(
                    """
                    MERGE (r:TestReport {report_id: $report_id})
                    SET r += $props
                    WITH r
                    MATCH (m:Material {material_id: $material_id})
                    MERGE (m)-[:HAS_TEST_REPORT]->(r)
                    """,
                    {
                        "report_id": record["report_id"],
                        "material_id": record["material_id"],
                        "props": self._normalize_neo4j_properties(record),
                    },
                ).consume()
                return

            session.run(
                """
                MERGE (d:SourceDocument {document_id: $document_id})
                SET d += $props
                WITH d
                MATCH (m:Material {material_id: $material_id})
                MERGE (m)-[:HAS_DOCUMENT]->(d)
                """,
                {
                    "document_id": record["document_id"],
                    "material_id": record["material_id"],
                    "props": self._normalize_neo4j_properties(record),
                },
            ).consume()

    def relationship_preview(self, material_id: str | None = None) -> list[dict[str, Any]]:
        query = """
        MATCH (a)-[r]-(b)
        WHERE $material_id IS NULL
            OR a.material_id = $material_id
            OR b.material_id = $material_id
        RETURN labels(a)[0] AS from_label,
               properties(a) AS from_props,
               type(r) AS type,
               labels(b)[0] AS to_label,
               properties(b) AS to_props
        LIMIT 80
        """
        rows = self._run_graph_query("relationship_preview", query, {"material_id": material_id})
        preview: list[dict[str, Any]] = []
        for row in rows:
            preview.append(
                {
                    "from": self._extract_node_id(row["from_label"], row["from_props"]),
                    "to": self._extract_node_id(row["to_label"], row["to_props"]),
                    "type": row["type"],
                }
            )
        return preview

    def graph_subgraph(self, material_id: str) -> dict[str, Any]:
        query = """
        MATCH (m:Material {material_id: $material_id})-[r]-(n)
        RETURN labels(startNode(r))[0] AS source_label,
               properties(startNode(r)) AS source_props,
               labels(endNode(r))[0] AS target_label,
               properties(endNode(r)) AS target_props,
               type(r) AS type
        """
        rows = self._run_graph_query("graph_subgraph", query, {"material_id": material_id})
        nodes = {material_id: self._node_descriptor(material_id)}
        edges: list[dict[str, Any]] = []
        for row in rows:
            source = self._normalize_node(row["source_label"], row["source_props"])
            target = self._normalize_node(row["target_label"], row["target_props"])
            nodes[source["id"]] = source
            nodes[target["id"]] = target
            edges.append({"source": source["id"], "target": target["id"], "type": row["type"]})
        return {"nodes": list(nodes.values()), "edges": edges}

    def graph_path(self, source_id: str, target_id: str) -> dict[str, Any]:
        query = """
        MATCH (source)
        WHERE any(k IN $id_keys WHERE source[k] = $source_id)
        MATCH (target)
        WHERE any(k IN $id_keys WHERE target[k] = $target_id)
        MATCH p = shortestPath((source)-[*..6]-(target))
        RETURN [node IN nodes(p) | {label: labels(node)[0], props: properties(node)}] AS nodes,
               [rel IN relationships(p) | {
                    type: type(rel),
                    source_label: labels(startNode(rel))[0],
                    source_props: properties(startNode(rel)),
                    target_label: labels(endNode(rel))[0],
                    target_props: properties(endNode(rel))
               }] AS edges
        """
        rows = self._run_graph_query(
            "graph_path",
            query,
            {"source_id": source_id, "target_id": target_id, "id_keys": self.ID_KEYS},
        )
        if not rows:
            return {"path": [], "edges": []}
        row = rows[0]
        path = [self._normalize_node(item["label"], item["props"]) for item in row["nodes"]]
        edges = [
            {
                "source": self._extract_node_id(item["source_label"], item["source_props"]),
                "target": self._extract_node_id(item["target_label"], item["target_props"]),
                "type": item["type"],
            }
            for item in row["edges"]
        ]
        return {"path": path, "edges": edges}

    def graph_node_insight(self, node_id: str) -> dict[str, Any]:
        insight = super().graph_node_insight(node_id)
        query = """
        MATCH (node)
        WHERE any(k IN $id_keys WHERE node[k] = $node_id)
        OPTIONAL MATCH (node)-[r]-(other)
        RETURN type(r) AS relationship_type,
               labels(other)[0] AS other_label,
               properties(other) AS other_props
        """
        rows = self._run_graph_query("graph_node_insight", query, {"node_id": node_id, "id_keys": self.ID_KEYS})
        relationship_counts: dict[str, int] = defaultdict(int)
        related: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            rel_type = row.get("relationship_type")
            if not rel_type or not row.get("other_label") or row.get("other_props") is None:
                continue
            relationship_counts[rel_type] += 1
            node = self._normalize_node(row["other_label"], row["other_props"])
            if node["id"] in seen:
                continue
            seen.add(node["id"])
            related.append(
                {
                    "id": node["id"],
                    "label": node["label"],
                    "type": node["type"],
                    "relationship": rel_type,
                }
            )
        insight["relationship_counts"] = [
            {"label": item_type.replace("_", " ").title(), "value": count}
            for item_type, count in sorted(relationship_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        insight["related"] = related[:12]
        return insight

    def selected_material_lookup(self, material_id: str) -> dict[str, Any] | None:
        if not self.driver:
            return super().selected_material_lookup(material_id)
        query = """
        MATCH (m:Material {material_id: $material_id})
        OPTIONAL MATCH (m)-[:SUPPLIED_BY]->(s:Supplier)
        OPTIONAL MATCH (m)-[:HAS_DOCUMENT]->(d:SourceDocument)
        RETURN properties(m) AS material,
               collect(DISTINCT properties(s)) AS suppliers,
               collect(DISTINCT properties(d)) AS documents
        """
        rows = self._run_graph_query("selected_material_lookup", query, {"material_id": material_id})
        if not rows:
            return None
        row = rows[0]
        material = row.get("material")
        if not material:
            return None
        payload = super().get_material(material_id) or material
        payload["suppliers"] = [item for item in row.get("suppliers", []) if item.get("supplier_id")] or payload.get("suppliers", [])
        payload["documents"] = [item for item in row.get("documents", []) if item.get("document_id")] or payload.get("documents", [])
        return payload

    def selected_supplier_lookup(self, supplier_id: str) -> dict[str, Any] | None:
        if not self.driver:
            return super().selected_supplier_lookup(supplier_id)
        query = """
        MATCH (s:Supplier {supplier_id: $supplier_id})
        OPTIONAL MATCH (s)-[:SUPPLIES]->(m:Material)
        RETURN properties(s) AS supplier,
               collect(DISTINCT properties(m)) AS materials
        """
        rows = self._run_graph_query("selected_supplier_lookup", query, {"supplier_id": supplier_id})
        if not rows:
            return None
        row = rows[0]
        supplier = row.get("supplier")
        if not supplier:
            return None
        payload = super().get_supplier(supplier_id) or supplier
        payload["supplied_materials"] = [item for item in row.get("materials", []) if item.get("material_id")] or payload.get("supplied_materials", [])
        return payload

    def selected_entity_lookup(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.driver:
            return super().selected_entity_lookup(entity_type, entity_id, entity_name)
        if entity_type == "material" and entity_id:
            material = self.selected_material_lookup(entity_id)
            return {"entity": {"type": "material", "id": entity_id, "label": material.get("name", entity_id)}, "material": material} if material else None
        if entity_type == "supplier" and entity_id:
            supplier = self.selected_supplier_lookup(entity_id)
            return {"entity": {"type": "supplier", "id": entity_id, "label": supplier.get("name", entity_id)}, "supplier": supplier} if supplier else None
        query = """
        MATCH (n)
        WHERE ($entity_id IS NOT NULL AND any(k IN $id_keys WHERE n[k] = $entity_id))
           OR ($entity_name IS NOT NULL AND toLower(coalesce(n.name, n.title, "")) = toLower($entity_name))
        RETURN labels(n)[0] AS label, properties(n) AS props
        LIMIT 1
        """
        rows = self._run_graph_query(
            "selected_entity_lookup",
            query,
            {"entity_id": entity_id, "entity_name": entity_name, "id_keys": self.ID_KEYS},
        )
        if not rows:
            return super().selected_entity_lookup(entity_type, entity_id, entity_name)
        row = rows[0]
        resolved = self._normalize_node(row["label"], row["props"])
        return super().selected_entity_lookup(resolved["type"], resolved["id"], resolved["label"])

    def uploaded_record_lookup(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.driver:
            return super().uploaded_record_lookup(entity_type, entity_id, entity_name)
        if entity_type in {"component"}:
            return super().uploaded_record_lookup(entity_type, entity_id, entity_name)
        query = """
        MATCH (n)
        WHERE ($entity_id IS NOT NULL AND (n.document_id = $entity_id OR n.report_id = $entity_id))
           OR ($entity_name IS NOT NULL AND toLower(coalesce(n.title, "")) = toLower($entity_name))
        RETURN labels(n)[0] AS label, properties(n) AS props
        LIMIT 1
        """
        rows = self._run_graph_query(
            "uploaded_record_lookup",
            query,
            {"entity_id": entity_id, "entity_name": entity_name},
        )
        if not rows:
            return super().uploaded_record_lookup(entity_type, entity_id, entity_name)
        row = rows[0]
        label = row["label"]
        props = row["props"]
        if label == "SourceDocument":
            return {"record_type": "document", "record": self.document_detail(props.get("document_id", ""))}
        if label == "TestReport":
            return {"record_type": "report", "record": self.document_detail(props.get("report_id", ""))}
        return super().uploaded_record_lookup(entity_type, entity_id, entity_name)

    def backend_status(self) -> list[dict[str, Any]]:
        statuses = super().backend_status()
        statuses[0]["status"] = "ready" if self.connection_state == "connected" else self.connection_state
        return statuses

    def graph_health(self) -> dict[str, Any]:
        return {
            "backend": "neo4j",
            "uri": _safe_neo4j_uri(self.settings.neo4j_uri),
            "database": self.settings.neo4j_database,
            "connected": self.connection_state == "connected",
            "mode": self.connection_state,
        }

    def _run_graph_query(self, query_name: str, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not self.driver:
            raise GraphConnectionError("Neo4j is not connected. Live graph queries are unavailable.")
        params = parameters or {}
        try:
            with self.driver.session(database=self.settings.neo4j_database) as session:
                explain = session.run(f"EXPLAIN {query}", params)
                explain_summary = explain.consume()
                result = session.run(query, params)
                rows = [dict(record) for record in result]
                result_summary = result.consume()
        except Exception as exc:
            raise GraphQueryFailure(f"Neo4j query '{query_name}' failed against database {self.settings.neo4j_database}.") from exc
        self._write_query_audit(
            query_name=query_name,
            query=query,
            parameters=params,
            result_count=len(rows),
            plan=self._serialize_plan(getattr(explain_summary, "plan", None)),
            counters=self._serialize_counters(getattr(result_summary, "counters", None)),
        )
        return rows

    def _write_query_audit(
        self,
        query_name: str,
        query: str,
        parameters: dict[str, Any],
        result_count: int,
        plan: dict[str, Any] | None,
        counters: dict[str, Any],
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query_name": query_name,
            "backend": "neo4j",
            "database": self.settings.neo4j_database,
            "result_count": result_count,
            "parameters": parameters,
            "query": " ".join(query.split()),
            "plan": plan,
            "counters": counters,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _serialize_plan(self, plan) -> dict[str, Any] | None:
        if not plan:
            return None
        children = getattr(plan, "children", None) or []
        return {
            "operator_type": getattr(plan, "operator_type", None),
            "arguments": getattr(plan, "arguments", {}),
            "identifiers": getattr(plan, "identifiers", []),
            "children": [self._serialize_plan(child) for child in children],
        }

    def _normalize_node(self, label: str, props: dict[str, Any]) -> dict[str, Any]:
        node_id = self._extract_node_id(label, props)
        node_type = self.LABEL_TO_TYPE.get(label, label.lower())
        id_key = self.LABEL_TO_ID_KEY.get(label, "")
        label_value = (
            props.get("name")
            or props.get("title")
            or props.get(id_key)
            or node_id
        )
        return {"id": node_id, "label": label_value, "type": node_type}

    def _extract_node_id(self, label: str, props: dict[str, Any]) -> str:
        id_key = self.LABEL_TO_ID_KEY.get(label)
        if id_key and props.get(id_key):
            return str(props[id_key])
        for key in self.ID_KEYS:
            if props.get(key):
                return str(props[key])
        return str(props.get("id", "unknown"))

    def _serialize_counters(self, counters) -> dict[str, Any]:
        if counters is None:
            return {}
        return {
            "contains_updates": getattr(counters, "contains_updates", False),
            "nodes_created": getattr(counters, "nodes_created", 0),
            "nodes_deleted": getattr(counters, "nodes_deleted", 0),
            "relationships_created": getattr(counters, "relationships_created", 0),
            "relationships_deleted": getattr(counters, "relationships_deleted", 0),
            "properties_set": getattr(counters, "properties_set", 0),
            "labels_added": getattr(counters, "labels_added", 0),
            "labels_removed": getattr(counters, "labels_removed", 0),
            "indexes_added": getattr(counters, "indexes_added", 0),
            "indexes_removed": getattr(counters, "indexes_removed", 0),
            "constraints_added": getattr(counters, "constraints_added", 0),
            "constraints_removed": getattr(counters, "constraints_removed", 0),
        }

    def _normalize_neo4j_properties(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, dict):
                for nested_key, nested_value in self._flatten_nested_dict(value, prefix=key).items():
                    normalized[nested_key] = self._normalize_scalar_or_list(nested_value)
            else:
                normalized[key] = self._normalize_scalar_or_list(value)
        return normalized

    def _flatten_nested_dict(self, value: dict[str, Any], prefix: str) -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for nested_key, nested_value in value.items():
            composite_key = f"{prefix}_{nested_key}"
            if isinstance(nested_value, dict):
                flattened.update(self._flatten_nested_dict(nested_value, composite_key))
            else:
                flattened[composite_key] = nested_value
        return flattened

    def _normalize_scalar_or_list(self, value: Any) -> Any:
        if isinstance(value, list):
            if all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                return value
            return json.dumps(value, sort_keys=True)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return json.dumps(value, sort_keys=True)


def build_graph_repository(settings=None) -> LocalGraphRepository:
    settings = settings or get_settings()
    return Neo4jGraphRepository(settings)
