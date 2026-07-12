from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class DocumentIntelligenceService:
    def __init__(self, runtime_dir: Path, repository) -> None:
        self.runtime_dir = runtime_dir
        self.repository = repository
        self.uploads_dir = runtime_dir / "uploads"
        self.documents_path = runtime_dir / "uploaded_source_documents.json"
        self.reports_path = runtime_dir / "uploaded_test_reports.json"
        self.artifacts_path = runtime_dir / "uploaded_artifacts.json"

    def ensure_seed(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        for path in [self.documents_path, self.reports_path, self.artifacts_path]:
            if not path.exists():
                self._write_json(path, [])

    def upload(
        self,
        *,
        filename: str,
        content: bytes,
        document_type: str,
        material_id: str,
        supplier_id: str | None = None,
        title: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        uploaded_at = datetime.now(timezone.utc).isoformat()
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", filename).strip("-") or "uploaded-file"
        artifact_id = f"ART-{uuid4().hex[:10].upper()}"
        storage_name = f"{artifact_id}-{safe_name}"
        storage_path = self.uploads_dir / storage_name
        storage_path.write_bytes(content)

        extracted = self._extract_fields(
            filename=filename,
            content=content,
            document_type=document_type,
            material_id=material_id,
            supplier_id=supplier_id,
        )
        checksum = hashlib.sha256(content).hexdigest()[:16]
        artifact_record = {
            "artifact_id": artifact_id,
            "filename": filename,
            "storage_path": str(storage_path),
            "document_type": document_type,
            "material_id": material_id,
            "supplier_id": supplier_id,
            "owner_id": owner_id,
            "uploaded_at": uploaded_at,
            "checksum": checksum,
            "extracted_fields": extracted,
        }
        artifacts = self._read_json(self.artifacts_path, [])
        artifacts.append(artifact_record)
        self._write_json(self.artifacts_path, artifacts)

        if document_type == "lab_report":
            record = {
                "report_id": f"RPT-UP-{uuid4().hex[:8].upper()}",
                "title": title or extracted["title"],
                "material_id": material_id,
                "lab": extracted.get("lab") or "Uploaded Lab Source",
                "migration_status": extracted.get("migration_status") or "review-required",
                "test_date": extracted.get("issued_on") or uploaded_at[:10],
                "source_filename": filename,
                "artifact_id": artifact_id,
                "extraction_summary": extracted["summary"],
                "detected_terms": extracted["detected_terms"],
            }
            reports = self._read_json(self.reports_path, [])
            reports.append(record)
            self._write_json(self.reports_path, reports)
            self._ingest_graph_record(record, "test_report")
            return {"kind": "test_report", "record": record, "artifact": artifact_record}

        record = {
            "document_id": f"DOC-UP-{uuid4().hex[:8].upper()}",
            "title": title or extracted["title"],
            "document_type": document_type,
            "material_id": material_id,
            "supplier_id": supplier_id or extracted.get("supplier_id"),
            "issued_on": extracted.get("issued_on") or uploaded_at[:10],
            "checksum": checksum,
            "provenance_score": extracted.get("provenance_score", 91),
            "source_filename": filename,
            "artifact_id": artifact_id,
            "extraction_summary": extracted["summary"],
            "detected_terms": extracted["detected_terms"],
        }
        documents = self._read_json(self.documents_path, [])
        documents.append(record)
        self._write_json(self.documents_path, documents)
        self._ingest_graph_record(record, "document")
        return {"kind": "document", "record": record, "artifact": artifact_record}

    def _ingest_graph_record(self, record: dict[str, Any], kind: str) -> None:
        ingest = getattr(self.repository, "ingest_uploaded_artifact", None)
        if callable(ingest):
            ingest(record, kind)

    def _extract_fields(
        self,
        *,
        filename: str,
        content: bytes,
        document_type: str,
        material_id: str,
        supplier_id: str | None,
    ) -> dict[str, Any]:
        text = content.decode("utf-8", errors="ignore")
        normalized = f"{filename}\n{text[:20000]}"
        lower = normalized.lower()
        title = Path(filename).stem.replace("_", " ").replace("-", " ").strip().title() or "Uploaded evidence"
        date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", normalized)
        issued_on = date_match.group(1) if date_match else None

        detected_terms = []
        for token in [
            "migration",
            "food contact",
            "declaration",
            "specification",
            "compostable",
            "recyclable",
            "compliant",
            "non-compliant",
            "contract",
            "certification",
            "expiry",
            "lead time",
            "price",
        ]:
            if token in lower:
                detected_terms.append(token)

        material = self.repository.material_index.get(material_id)
        supplier = self.repository.supplier_index.get(supplier_id) if supplier_id else None
        if not supplier:
            supplier = next(
                (item for item in self.repository.suppliers if item["name"].lower() in lower or item["supplier_id"].lower() in lower),
                None,
            )
        migration_status = None
        if "pass" in lower or "approved" in lower or "compliant" in lower:
            migration_status = "pass"
        elif "fail" in lower or "non-compliant" in lower:
            migration_status = "fail"

        lab = None
        lab_match = re.search(r"lab[:\s]+([A-Za-z0-9 &._-]+)", normalized, re.IGNORECASE)
        if lab_match:
            lab = lab_match.group(1).strip()[:80]

        cert_name = None
        for cert in getattr(self.repository, "certifications", []):
            if cert["name"].lower() in lower:
                cert_name = cert["name"]
                break

        summary_bits = [document_type.replace("_", " ")]
        if material:
            summary_bits.append(material["name"])
        if supplier:
            summary_bits.append(supplier["name"])
        if cert_name:
            summary_bits.append(cert_name)
        if migration_status:
            summary_bits.append(f"migration {migration_status}")

        return {
            "title": title,
            "issued_on": issued_on,
            "supplier_id": supplier["supplier_id"] if supplier else supplier_id,
            "lab": lab,
            "migration_status": migration_status,
            "certification_name": cert_name,
            "provenance_score": 93 if detected_terms else 88,
            "detected_terms": detected_terms,
            "summary": " / ".join(summary_bits),
        }

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
