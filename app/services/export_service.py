from __future__ import annotations

import csv
import io
from typing import Any


class ExportService:
    def investigation_csv(self, investigation: dict[str, Any]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["field", "value"])
        writer.writerow(["investigation_id", investigation["investigation_id"]])
        writer.writerow(["title", investigation["title"]])
        writer.writerow(["focus_material_id", investigation.get("focus_material_id", "")])
        writer.writerow(["status", investigation.get("status", "")])
        writer.writerow(["notes", investigation.get("notes", "")])
        writer.writerow(["decision_rationale", investigation.get("decision_rationale", "")])
        writer.writerow(["shortlisted_material_ids", ", ".join(investigation.get("shortlisted_material_ids", []))])
        writer.writerow(["comparison_material_ids", ", ".join(investigation.get("comparison_material_ids", []))])
        return buffer.getvalue().encode("utf-8")

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
        safe_lines = [line.replace("(", "\\(").replace(")", "\\)") for line in lines]
        content = ["BT", "/F1 12 Tf", "50 780 Td"]
        first = True
        for line in safe_lines:
            if not first:
                content.append("0 -18 Td")
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
        pdf += (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1")
        )
        return pdf
