from __future__ import annotations

import csv
import io
from typing import Any


class ExportService:
    def investigation_csv(self, investigation: dict[str, Any]) -> bytes:
        return self._rows_to_csv(
            ["field", "value"],
            [
                ["investigation_id", investigation["investigation_id"]],
                ["title", investigation["title"]],
                ["focus_material_id", investigation.get("focus_material_id", "")],
                ["status", investigation.get("status", "")],
                ["notes", investigation.get("notes", "")],
                ["decision_rationale", investigation.get("decision_rationale", "")],
                ["shortlisted_material_ids", ", ".join(investigation.get("shortlisted_material_ids", []))],
                ["comparison_material_ids", ", ".join(investigation.get("comparison_material_ids", []))],
            ],
        )

    def investigation_pdf(self, investigation: dict[str, Any]) -> bytes:
        lines = [
            "PackGraph Lab Investigation Report",
            "",
            f"ID: {investigation['investigation_id']}",
            f"Title: {investigation['title']}",
            f"Focus material: {investigation.get('focus_material_id', '')}",
            f"Status: {investigation.get('status', '')}",
            "",
            "Notes:",
            investigation.get("notes", ""),
            "",
            "Decision rationale:",
            investigation.get("decision_rationale", ""),
            "",
            "Shortlisted materials:",
            ", ".join(investigation.get("shortlisted_material_ids", [])),
            "",
            "Comparison materials:",
            ", ".join(investigation.get("comparison_material_ids", [])),
        ]
        return self._simple_pdf(lines)

    def executive_summary_csv(self, payload: dict[str, Any]) -> bytes:
        material = payload["material"]
        rows = [
            ["material_id", material["material_id"]],
            ["name", material["name"]],
            ["category", material["category"]],
            ["composition", material["composition"]],
            ["compliance_state", material["compliance_state"]],
            ["sustainability_score", material["sustainability_score"]],
            ["recyclability_score", material["recyclability_score"]],
            ["compostability_score", material["compostability_score"]],
            ["cost_range", f"{material['cost_range']['low']} to {material['cost_range']['high']} {material['cost_range']['currency']}"],
            ["supplier_count", len(payload["suppliers"])],
            ["document_count", len(payload["documents"])],
            ["test_report_count", len(payload["test_reports"])],
            ["alert_count", len(payload["alerts"])],
        ]
        return self._rows_to_csv(["field", "value"], rows)

    def executive_summary_pdf(self, payload: dict[str, Any]) -> bytes:
        material = payload["material"]
        lines = [
            "PackGraph Lab Executive Summary",
            "",
            f"Material: {material['name']} ({material['category']})",
            f"Composition: {material['composition']}",
            f"Compliance state: {material['compliance_state']}",
            f"Sustainability: {material['sustainability_score']}",
            f"Recyclability: {material['recyclability_score']}",
            f"Compostability: {material['compostability_score']}",
            f"Cost range: {material['cost_range']['low']} to {material['cost_range']['high']} {material['cost_range']['currency']}",
            "",
            "Qualified suppliers:",
            *[f"- {item['name']} | ESG {item['esg_score']} | risk {item['disruption_risk_score']}" for item in payload["suppliers"][:5]],
            "",
            "Current alerts:",
            *([f"- {item['title']}: {item['detail']}" for item in payload["alerts"][:5]] or ["- No active alerts for this material."]),
        ]
        return self._simple_pdf(lines)

    def compliance_pack_csv(self, payload: dict[str, Any]) -> bytes:
        material = payload["material"]
        rows = []
        for regulation in payload["regulations"]:
            rows.append(
                [
                    material["name"],
                    regulation["name"],
                    "active" if regulation["active"] else "upcoming",
                    regulation["effective_date"],
                    regulation["focus"],
                ]
            )
        if not rows:
            rows.append([material["name"], "No linked regulations", "", "", ""])
        return self._rows_to_csv(
            ["material", "regulation", "status", "effective_date", "focus"],
            rows,
        )

    def compliance_pack_pdf(self, payload: dict[str, Any]) -> bytes:
        material = payload["material"]
        lines = [
            "PackGraph Lab Compliance Pack",
            "",
            f"Material: {material['name']}",
            f"Compliance state: {material['compliance_state']}",
            "",
            "Linked regulations:",
            *(
                [
                    f"- {item['name']} | {'active' if item['active'] else 'upcoming'} | effective {item['effective_date']}"
                    for item in payload["regulations"]
                ]
                or ["- No linked regulations in the current graph."]
            ),
            "",
            "Evidence set:",
            f"- Documents: {len(payload['documents'])}",
            f"- Test reports: {len(payload['test_reports'])}",
            "",
            "Open alert context:",
            *([f"- {item['title']}" for item in payload["alerts"][:6]] or ["- No active alerts."]),
        ]
        return self._simple_pdf(lines)

    def supplier_comparison_csv(self, suppliers: list[dict[str, Any]]) -> bytes:
        rows = [
            [
                item["supplier_id"],
                item["name"],
                item["country"],
                item["disruption_risk_score"],
                item["esg_score"],
                item["lead_time_days"],
                item.get("average_cost_pressure"),
                item.get("average_compliance_rate"),
            ]
            for item in suppliers
        ]
        return self._rows_to_csv(
            [
                "supplier_id",
                "name",
                "country",
                "risk_score",
                "esg_score",
                "lead_time_days",
                "average_cost_pressure",
                "average_compliance_rate",
            ],
            rows,
        )

    def supplier_comparison_pdf(self, suppliers: list[dict[str, Any]]) -> bytes:
        lines = ["PackGraph Lab Supplier Comparison Snapshot", ""]
        for supplier in suppliers:
            lines.extend(
                [
                    f"{supplier['name']} ({supplier['country']})",
                    f"Risk {supplier['disruption_risk_score']} | ESG {supplier['esg_score']} | Lead time {supplier['lead_time_days']} days",
                    f"Average cost pressure {supplier.get('average_cost_pressure')} | compliance rate {supplier.get('average_compliance_rate')}",
                    "",
                ]
            )
        if len(lines) == 2:
            lines.append("No suppliers selected.")
        return self._simple_pdf(lines)

    def _rows_to_csv(self, header: list[str], rows: list[list[Any]]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8")

    def _simple_pdf(self, lines: list[str]) -> bytes:
        safe_lines = [str(line).replace("(", "\\(").replace(")", "\\)") for line in lines]
        content = ["BT", "/F1 11 Tf", "50 780 Td"]
        first = True
        for line in safe_lines:
            if not first:
                content.append("0 -16 Td")
            content.append(f"({line}) Tj")
            first = False
        content.append("ET")
        stream = "\n".join(content).encode("latin-1", errors="replace")
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
            f"4 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1") + stream + b"\nendstream endobj",
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        ]
        pdf = b"%PDF-1.4\n"
        offsets = []
        for obj in objects:
            offsets.append(len(pdf))
            pdf += obj + b"\n"
        xref_start = len(pdf)
        pdf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
        pdf += b"0000000000 65535 f \n"
        for offset in offsets:
            pdf += f"{offset:010d} 00000 n \n".encode("latin-1")
        pdf += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1")
        return pdf
