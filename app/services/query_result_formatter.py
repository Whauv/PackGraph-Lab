from __future__ import annotations

from typing import Any


class QueryResultFormatter:
    def __init__(self, repository) -> None:
        self.repository = repository

    def summarize_selected_material_lookup(self, material: dict[str, Any] | None, material_id: str | None) -> str:
        if not material:
            return f"The graph query completed, but no material node matched {material_id or 'the selected context'}."
        return self.summarize_material_detail(material)

    def summarize_selected_supplier_lookup(self, supplier: dict[str, Any] | None, supplier_id: str | None) -> str:
        if not supplier:
            return f"The graph query completed, but no supplier node matched {supplier_id or 'the selected context'}."
        return (
            f"{supplier['name']} serves {', '.join(supplier.get('regions_served', [])[:3])} with lead time {supplier.get('lead_time_days', 'n/a')} days.\n"
            f"Disruption risk {supplier.get('disruption_risk_score', 'n/a')} | ESG {supplier.get('esg_score', 'n/a')} | "
            f"Supplied materials {len(supplier.get('supplied_materials', []))}."
        )

    def summarize_selected_entity_lookup(self, payload: dict[str, Any] | None) -> str:
        if not payload or not payload.get("entity"):
            return "The graph query completed, but the selected entity could not be resolved against likely graph labels."
        entity = payload["entity"]
        if entity["type"] == "material" and payload.get("material"):
            return self.summarize_material_detail(payload["material"])
        if entity["type"] == "supplier" and payload.get("supplier"):
            return self.summarize_selected_supplier_lookup(payload["supplier"], entity["id"])
        if entity["type"] in {"document", "report"} and payload.get("document"):
            document = payload["document"]
            return f"{document.get('title', entity['label'])} is available as selected evidence with confidence {document.get('confidence_summary', 'n/a')}."
        if entity["type"] == "component" and payload.get("component"):
            component = payload["component"]
            return f"{component.get('name', entity['label'])} is stored as a discovered component for future packaging lookups."
        return f"Resolved the selected entity as {entity['label']} ({entity['type']})."

    def summarize_uploaded_record_lookup(self, payload: dict[str, Any] | None) -> str:
        if not payload or not payload.get("record"):
            return "The lookup completed, but no uploaded or source-backed record matched the selected context."
        record = payload["record"]
        record_type = payload.get("record_type", "record")
        if record_type == "component":
            return f"{record.get('name', 'Selected component')} is stored as a discovered component with related material links."
        return f"{record.get('title', 'Selected evidence')} is available as a {record_type} with extracted fields and confidence metadata."

    def summarize_material_list(self, materials: list[dict[str, Any]], intro: str) -> str:
        if not materials:
            return f"{intro}: no matching materials were found in the current synthetic dataset."
        lines = []
        for item in materials[:4]:
            if "material_id" in item and item["material_id"] in self.repository.material_index:
                material = self.repository.material_index[item["material_id"]]
                lines.append(
                    f"{material['name']} ({material['category']}) | sustainability {material['sustainability_score']} | "
                    f"recyclability {material['recyclability_score']} | compliance {material['compliance_state']}"
                )
            else:
                lines.append(str(item))
        return f"{intro}:\n" + "\n".join(lines)

    def summarize_supplier_list(self, suppliers: list[dict[str, Any]], intro: str) -> str:
        if not suppliers:
            return f"{intro}: no matching suppliers were found."
        return f"{intro}:\n" + "\n".join(
            f"{item['name']} | risk {item['disruption_risk_score']} | ESG {item['esg_score']} | lead time {item['lead_time_days']} days"
            for item in suppliers[:4]
        )

    def summarize_risk_materials(self, materials: list[dict[str, Any]]) -> str:
        if not materials:
            return "No high-risk materials were found in the current dataset."
        return "Most exposed materials in the current synthetic graph:\n" + "\n".join(
            f"{item['name']} | average supplier risk {item['supplier_risk_score']}" for item in materials
        )

    def summarize_evidence(self, payload: dict[str, Any]) -> str:
        if not payload or not payload.get("material"):
            return "No evidence bundle was found for that material."
        material = payload["material"]
        documents = payload.get("documents", [])
        reports = payload.get("test_reports", [])
        return (
            f"Evidence for {material['name']}: {len(documents)} source documents and {len(reports)} test reports.\n"
            + "\n".join(f"{item['title']}" for item in documents[:3] + reports[:2])
        )

    def summarize_material_detail(self, material: dict[str, Any] | None) -> str:
        if not material:
            return "That material could not be found in the demo graph."
        return (
            f"{material['name']} is a {material['category']} material made from {material['composition']}.\n"
            f"Sustainability {material['sustainability_score']}, recyclability {material['recyclability_score']}, "
            f"compliance {material['compliance_state']}, suppliers {len(material['suppliers'])}."
        )

    def summarize_comparison(self, results: list[dict[str, Any]]) -> str:
        if not results:
            return "I could not compare materials because the question did not include enough named candidates."
        return "Material comparison from the demo ranking model:\n" + "\n".join(
            f"{item['name']} | weighted score {item['weighted_score']} | sustainability {item['scores']['sustainability']} | recyclability {item['scores']['recyclability']}"
            for item in results[:4]
        )

    def normalize_result_rows(self, result: Any, source: str) -> list[dict[str, Any]]:
        if isinstance(result, list):
            rows = []
            for item in result[:10]:
                if isinstance(item, dict):
                    row = {key: value for key, value in item.items() if isinstance(value, (str, int, float, bool)) or value is None}
                    rows.append(row)
            return rows
        if isinstance(result, dict):
            rows = []
            if source in {"private_data", "source_intake"}:
                for item in result.get("rows", [])[:10]:
                    fields = item.get("fields", [])
                    if source == "source_intake":
                        fields = [
                            {"label": field.get("path", "field"), "value": ", ".join(field.get("types", []))}
                            for field in item.get("schema_fields", [])[:3]
                        ]
                    rows.append(
                        {
                            "entity_type": item.get("entity_type"),
                            "entity_id": item.get("entity_id"),
                            "label": item.get("label"),
                            "score": item.get("score"),
                            "preview": item.get("preview") or " | ".join(f"{field['label']}: {field['value']}" for field in fields[:3]),
                        }
                    )
                return rows
            if result.get("material"):
                material = result["material"]
                rows.append(
                    {
                        "entity_type": "material",
                        "entity_id": material.get("material_id"),
                        "label": material.get("name"),
                        "score": material.get("sustainability_score"),
                        "preview": f"{material.get('category', '')} | compliance {material.get('compliance_state', '')}",
                    }
                )
            if result.get("supplier"):
                supplier = result["supplier"]
                rows.append(
                    {
                        "entity_type": "supplier",
                        "entity_id": supplier.get("supplier_id"),
                        "label": supplier.get("name"),
                        "score": max(1, 100 - float(supplier.get("disruption_risk_score", 0) or 0)),
                        "preview": f"Lead time {supplier.get('lead_time_days', 'n/a')} | risk {supplier.get('disruption_risk_score', 'n/a')}",
                    }
                )
            if result.get("entity"):
                entity = result["entity"]
                rows.append(
                    {
                        "entity_type": entity.get("type"),
                        "entity_id": entity.get("id"),
                        "label": entity.get("label"),
                        "score": 100,
                        "preview": f"Resolved selected {entity.get('type', 'entity')}",
                    }
                )
            if result.get("record"):
                record = result["record"]
                rows.append(
                    {
                        "entity_type": result.get("record_type", "record"),
                        "entity_id": record.get("document_id") or record.get("report_id") or record.get("component_id"),
                        "label": record.get("title") or record.get("name"),
                        "score": 100,
                        "preview": record.get("preview_text") or record.get("summary") or "Selected uploaded record",
                    }
                )
            return rows
        return []
