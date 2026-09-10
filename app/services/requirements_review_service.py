from __future__ import annotations

from typing import Any


class RequirementsReviewService:
    def normalize(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if not context:
            return {}
        raw = context.get("requirements") or {}
        if not isinstance(raw, dict):
            return {}
        return {
            "application": self._clean(raw.get("application")),
            "constraints": self._clean(raw.get("constraints")),
            "region": self._clean(raw.get("region")),
            "priorities": self._clean(raw.get("priorities")),
            "notes": self._clean(raw.get("notes")),
        }

    def build_review(
        self,
        *,
        requirements: dict[str, Any],
        rows: list[dict[str, Any]],
        evidence_profile: dict[str, Any],
        missing_evidence: list[str],
        mode: str,
    ) -> dict[str, Any]:
        if mode != "research_review" and not any(requirements.values()):
            return {}
        if not any(requirements.values()):
            return {
                "fit": "needs_requirements",
                "application": "",
                "constraints": "",
                "region": "",
                "reason": "Research Review mode works best after application, constraints, region, and priorities are saved.",
                "risks": ["No saved requirements were provided for this review."],
                "next_step": "Save requirements in the Graph Chat drawer, then run Research Review again.",
                "dimensions": self._dimensions(rows, evidence_profile, missing_evidence, requirements),
            }

        dimensions = self._dimensions(rows, evidence_profile, missing_evidence, requirements)
        average = sum(dimensions.values()) / len(dimensions)
        fit = "strong_fit" if average >= 76 else "conditional_fit" if average >= 55 else "weak_fit"
        risks = []
        if dimensions["supplier_risk"] < 60:
            risks.append("Supplier coverage or risk needs review for the selected region.")
        if dimensions["evidence_strength"] < 60:
            risks.append("Evidence is not strong enough for approval without source follow-up.")
        if missing_evidence:
            risks.extend(missing_evidence[:2])
        return {
            "fit": fit,
            "application": requirements.get("application", ""),
            "constraints": requirements.get("constraints", ""),
            "region": requirements.get("region", ""),
            "reason": self._reason(fit, requirements, dimensions),
            "risks": risks,
            "next_step": "Compare selected against requirements." if rows else "Stage a review task for the missing graph relationship.",
            "dimensions": dimensions,
        }

    def build_audit(
        self,
        *,
        selected_material: dict[str, Any] | None,
        requirements: dict[str, Any],
        route: str,
        confidence: float,
        evidence_count: int,
        missing_evidence: list[str],
        enrichment_request: dict[str, Any] | None,
    ) -> dict[str, Any]:
        missing_fields = [key for key, value in requirements.items() if not value]
        return {
            "selected_material": selected_material or {},
            "requirements_used": any(requirements.values()),
            "graph_route_used": route,
            "confidence": round(float(confidence or 0), 2),
            "evidence_count": evidence_count,
            "missing_fields": missing_fields,
            "missing_evidence_count": len(missing_evidence),
            "provisional_status": "pending_review" if enrichment_request else "none",
        }

    def _dimensions(self, rows: list[dict[str, Any]], evidence_profile: dict[str, Any], missing_evidence: list[str], requirements: dict[str, Any]) -> dict[str, int]:
        top_score = max([float(row.get("score", 0) or 0) for row in rows], default=0)
        normalized_score = int(round(top_score if top_score <= 100 else 100))
        evidence_score = {"strong": 88, "moderate": 68, "weak": 38}.get(evidence_profile.get("evidence_strength"), 40)
        if missing_evidence:
            evidence_score = max(20, evidence_score - 12)
        requirements_bonus = 8 if requirements.get("application") else 0
        region_bonus = 6 if requirements.get("region") else 0
        return {
            "technical_fit": min(100, max(35, normalized_score + requirements_bonus)),
            "sustainability_fit": min(100, max(35, normalized_score + (6 if "sustain" in str(requirements.get("priorities", "")).lower() else 0))),
            "supplier_risk": min(100, max(35, 72 + region_bonus - (10 if not rows else 0))),
            "evidence_strength": evidence_score,
            "application_match": min(100, max(35, 70 + requirements_bonus + region_bonus - (12 if not rows else 0))),
        }

    def _reason(self, fit: str, requirements: dict[str, Any], dimensions: dict[str, int]) -> str:
        label = fit.replace("_", " ")
        return (
            f"PackGraph rated this as a {label} for {requirements.get('application') or 'the saved use case'} "
            f"because application match is {dimensions['application_match']} and evidence strength is {dimensions['evidence_strength']}."
        )

    def _clean(self, value: Any) -> str:
        return str(value or "").strip()[:600]
