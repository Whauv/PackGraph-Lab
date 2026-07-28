from __future__ import annotations

from typing import Any


class EvidenceAgent:
    def build_profile(
        self,
        *,
        result: Any,
        evidence_rows: list[dict[str, Any]],
        proof_requested: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        document_count = len(evidence_rows)
        missing = []
        if proof_requested and document_count == 0:
            missing.append("No supporting document, declaration, or report was found for this proof-oriented request.")

        if isinstance(result, dict) and result.get("material") and not result.get("documents"):
            missing.append("Material detail exists, but no linked source documents were returned.")

        evidence_strength = "strong" if document_count >= 3 else "moderate" if document_count >= 1 else "weak"
        confidence = 0.9 if evidence_strength == "strong" else 0.72 if evidence_strength == "moderate" else 0.48
        profile = {
            "document_count": document_count,
            "evidence_strength": evidence_strength,
            "confidence": round(confidence, 2),
            "proof_requested": proof_requested,
            "source_document_lookup_signal": document_count > 0,
            "explanation": f"Evidence strength is {evidence_strength} based on {document_count} linked document rows.",
        }
        return profile, missing
