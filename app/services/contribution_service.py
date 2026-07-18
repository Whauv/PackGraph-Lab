from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ContributionService:
    ROLE_CONFIG = [
        {
            "role_id": "fellow",
            "title": "Fellow",
            "persona": "Scientist or researcher",
            "verification_level": "Verified domain contributor",
            "badge": "Lab-backed",
            "description": "Contribute test interpretation, material insight, and evidence-backed corrections.",
            "permissions": [
                "Submit material performance insight",
                "Upload source or evidence placeholder",
                "Suggest profile edits with rationale",
                "Propose substitute or application links",
            ],
        },
        {
            "role_id": "curator",
            "title": "Curator",
            "persona": "Expert communicator or industry translator",
            "verification_level": "Reviewed translator",
            "badge": "Signal shaper",
            "description": "Translate technical material signals into usable product guidance for broader audiences.",
            "permissions": [
                "Summarize technical findings",
                "Frame evidence for operations teams",
                "Suggest supplier and application links",
                "Flag missing documentation or context",
            ],
        },
        {
            "role_id": "explorer",
            "title": "Explorer",
            "persona": "Student, builder, or general user",
            "verification_level": "Open contributor",
            "badge": "Field observer",
            "description": "Share exploratory findings, ask good questions, and surface useful links from the wider ecosystem.",
            "permissions": [
                "Suggest profile edits",
                "Propose supplier or application links",
                "Share source references",
                "Track submission status and badge progression",
            ],
        },
    ]

    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "contributions.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)

    def ensure_seed(self) -> None:
        if self.path.exists():
            return
        self._write(
            [
                {
                    "contribution_id": "CON-001",
                    "role_id": "fellow",
                    "submission_type": "material_insight",
                    "title": "Clarify oxygen barrier note for Film A11",
                    "summary": "Submitted updated interpretation on barrier behavior in chilled meal use cases.",
                    "related_entity_type": "material",
                    "related_entity_id": "MAT-001",
                    "status": "under_review",
                    "verification_level": "Verified domain contributor",
                    "badge": "Lab-backed",
                    "submitted_by": "Demo Analyst",
                    "submitted_on": "2026-07-14T10:15:00",
                    "evidence_confidence": 86,
                    "diff_preview": {
                        "before": "Barrier note says suitable for chilled food-service trays.",
                        "after": "Barrier note now distinguishes chilled trays from longer-shelf meal pouches.",
                    },
                    "reviewer_note": "Needs one more declaration cross-check before acceptance.",
                },
                {
                    "contribution_id": "CON-002",
                    "role_id": "curator",
                    "submission_type": "supplier_link",
                    "title": "Suggest stronger supplier-to-application framing for medical peel packs",
                    "summary": "Added context connecting documentation strength and supplier selection in regulated packaging flows.",
                    "related_entity_type": "application",
                    "related_entity_id": "APP-017",
                    "status": "accepted",
                    "verification_level": "Reviewed translator",
                    "badge": "Signal shaper",
                    "submitted_by": "Compliance Lead",
                    "submitted_on": "2026-07-11T14:40:00",
                    "evidence_confidence": 91,
                    "diff_preview": {
                        "before": "Supplier links based on cost and availability only.",
                        "after": "Supplier links now include declaration strength and audit-readiness context.",
                    },
                    "reviewer_note": "Accepted for stronger evidence framing.",
                },
                {
                    "contribution_id": "CON-003",
                    "role_id": "explorer",
                    "submission_type": "source_upload",
                    "title": "Reference note on compostable pouch evidence gaps",
                    "summary": "Added a source pointer highlighting declaration coverage issues in compostable snack packaging.",
                    "related_entity_type": "news",
                    "related_entity_id": "NEWS-002",
                    "status": "queued",
                    "verification_level": "Open contributor",
                    "badge": "Field observer",
                    "submitted_by": "Demo Analyst",
                    "submitted_on": "2026-07-09T09:05:00",
                    "evidence_confidence": 62,
                    "diff_preview": {
                        "before": "News item mentions sustainability pressure only.",
                        "after": "News item now calls out declaration and test-report gaps as part of the update.",
                    },
                    "reviewer_note": "",
                },
            ]
        )

    def list_roles(self) -> list[dict[str, Any]]:
        return self.ROLE_CONFIG

    def list_submissions(self) -> list[dict[str, Any]]:
        return sorted(self._read(), key=lambda item: item.get("submitted_on", ""), reverse=True)

    def list_queue(self) -> list[dict[str, Any]]:
        return [item for item in self.list_submissions() if item.get("status") in {"queued", "under_review"}]

    def status_summary(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {"queued": 0, "under_review": 0, "accepted": 0, "rejected": 0}
        for record in self._read():
            status = record.get("status", "queued")
            counts[status] = counts.get(status, 0) + 1
        return [{"label": key.replace("_", " ").title(), "value": value} for key, value in counts.items()]

    def create(self, payload: dict[str, Any], submitted_by: str) -> dict[str, Any]:
        role = next((item for item in self.ROLE_CONFIG if item["role_id"] == payload["role_id"]), self.ROLE_CONFIG[-1])
        records = self._read()
        record = {
            "contribution_id": f"CON-{len(records) + 1:03d}",
            **payload,
            "status": "queued",
            "verification_level": role["verification_level"],
            "badge": role["badge"],
            "submitted_by": submitted_by,
            "submitted_on": datetime.now().isoformat(timespec="seconds"),
            "evidence_confidence": self._score_confidence(payload),
            "diff_preview": {
                "before": payload.get("edit_request", "") or "No prior draft was attached.",
                "after": payload.get("summary", "") or payload.get("proposed_links", "") or "Contribution submitted.",
            },
            "reviewer_note": "",
        }
        records.append(record)
        self._write(records)
        return record

    def review(self, contribution_id: str, status: str, reviewer_name: str, reviewer_note: str) -> dict[str, Any] | None:
        records = self._read()
        updated = None
        for record in records:
            if record["contribution_id"] != contribution_id:
                continue
            record["status"] = status
            record["reviewer_name"] = reviewer_name
            record["reviewed_on"] = datetime.now().isoformat(timespec="seconds")
            record["reviewer_note"] = reviewer_note.strip()
            updated = record
            break
        if not updated:
            return None
        self._write(records)
        return updated

    def _score_confidence(self, payload: dict[str, Any]) -> int:
        score = 55
        if payload.get("summary"):
            score += 10
        if payload.get("evidence_note"):
            score += 15
        if payload.get("edit_request"):
            score += 10
        if payload.get("proposed_links"):
            score += 10
        return min(score, 98)
