from __future__ import annotations

from datetime import datetime, UTC
import hashlib
import json
import re
from typing import Any

from app.core.config import Settings, get_settings
from app.services.security_utils import sanitize_audit_payload, secure_append_jsonl, secure_write_json


class MatchDecisionCache:
    def __init__(self, path):
        self.path = path
        if not self.path.exists():
            secure_write_json(self.path, {})

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            secure_write_json(self.path, {})
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def get(self, key: str) -> dict[str, Any] | None:
        return self.load().get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        payload = self.load()
        payload[key] = value
        secure_write_json(self.path, payload)


class EntityResolutionAgent:
    SYNONYMS = {
        "aluminium": "aluminum",
        "polyethylene": "pe",
        "poly ethylene": "pe",
        "polypropylene": "pp",
        "post consumer recycled": "pcr",
        "post-consumer recycled": "pcr",
        "food safe": "food contact",
        "food-safe": "food contact",
        "gmbh": "",
        "inc": "",
        "ltd": "",
    }

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.cache = MatchDecisionCache(self.settings.match_decision_cache_path)
        self.audit_path = self.settings.entity_resolution_audit_path
        self.active_backend = self._resolve_backend()

    def analyze(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        comparisons = []
        for index, left in enumerate(rows):
            for right in rows[index + 1 :]:
                if self._row_kind(left) != self._row_kind(right):
                    continue
                comparison = self.compare_records(left, right)
                if comparison["decision"] != "reject_match":
                    comparisons.append(comparison)

        review_items = [item for item in comparisons if item["decision"] == "review_before_merge"]
        auto_items = [item for item in comparisons if item["decision"] == "auto_commit"]
        return {
            "checked_rows": len(rows),
            "backend": self.active_backend,
            "duplicate_groups": comparisons,
            "auto_commit_candidates": auto_items,
            "review_candidates": review_items,
            "review_before_merge": bool(review_items),
        }

    def compare_records(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        pair_key = self._pair_key(left, right)
        left_label = self._label_for_row(left)
        right_label = self._label_for_row(right)
        cached = self.cache.get(pair_key)
        if cached:
            return {
                **cached,
                "left_label": left_label,
                "right_label": right_label,
                "pair_key": pair_key,
                "decision_source": "cache",
            }

        lexical = self._token_similarity(left_label, right_label)
        numeric = self._numeric_similarity(left, right)
        score = round((lexical * 0.75) + (numeric * 0.25), 3)
        if score >= self.settings.er_auto_accept_threshold:
            decision = "auto_commit"
        elif score >= self.settings.er_review_threshold:
            decision = "review_before_merge"
        else:
            decision = "reject_match"
        result = {
            "left_label": left_label,
            "right_label": right_label,
            "confidence": score,
            "decision": decision,
            "backend": self.active_backend,
            "score_breakdown": {
                "lexical_similarity": round(lexical, 3),
                "numeric_similarity": round(numeric, 3),
                "decision_thresholds": {
                    "review": self.settings.er_review_threshold,
                    "auto_commit": self.settings.er_auto_accept_threshold,
                },
            },
            "reason": f"Lexical similarity {lexical:.2f}, numeric similarity {numeric:.2f}.",
        }
        self.cache.set(
            pair_key,
            {
                "confidence": result["confidence"],
                "decision": result["decision"],
                "backend": result["backend"],
                "score_breakdown": result["score_breakdown"],
                "reason": result["reason"],
            },
        )
        self._append_audit(pair_key, result)
        return {**result, "pair_key": pair_key, "decision_source": self.active_backend}

    def _append_audit(self, pair_key: str, result: dict[str, Any]) -> None:
        entry = sanitize_audit_payload({"timestamp": datetime.now(UTC).isoformat(), "pair_key": pair_key, **result})
        secure_append_jsonl(self.audit_path, entry)

    def _pair_key(self, left: dict[str, Any], right: dict[str, Any]) -> str:
        labels = sorted([self._label_for_row(left), self._label_for_row(right)])
        payload = json.dumps(
            {
                "kind": self._row_kind(left),
                "labels": labels,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _resolve_backend(self) -> str:
        configured = (self.settings.er_backend or "heuristic").strip().lower()
        if configured in {"heuristic", "local"}:
            return configured
        if not self.settings.llm_enabled:
            return "heuristic"
        return configured

    def _label_for_row(self, row: dict[str, Any]) -> str:
        return str(
            row.get("name")
            or row.get("title")
            or row.get("label")
            or row.get("entity_id")
            or row.get("material_id")
            or row.get("supplier_id")
            or row.get("preview")
            or ""
        ).strip()

    def _row_kind(self, row: dict[str, Any]) -> str:
        return str(row.get("entity_type") or row.get("type") or "record")

    def _normalize_text(self, value: str) -> str:
        text = value.casefold()
        for source, target in self.SYNONYMS.items():
            text = text.replace(source, target)
        text = re.sub(r"[^a-z0-9.%/ ]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _token_similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._normalize_text(left).split())
        right_tokens = set(self._normalize_text(right).split())
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / union if union else 0.0

    def _numeric_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        comparable = 0
        matched = 0.0
        for key in set(left.keys()) & set(right.keys()):
            left_numeric = self._parse_numeric_with_unit(left.get(key))
            right_numeric = self._parse_numeric_with_unit(right.get(key))
            if not left_numeric or not right_numeric:
                continue
            comparable += 1
            if left_numeric["unit"] == right_numeric["unit"]:
                if left_numeric["value"] == right_numeric["value"]:
                    matched += 1.0
                else:
                    delta = abs(left_numeric["value"] - right_numeric["value"])
                    scale = max(abs(left_numeric["value"]), abs(right_numeric["value"]), 1.0)
                    matched += max(0.0, 1.0 - (delta / scale))
        if comparable == 0:
            return 0.0
        return matched / comparable

    def _parse_numeric_with_unit(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, (int, float)):
            return {"value": float(value), "unit": ""}
        if not isinstance(value, str):
            return None
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*([a-z%/]+)?", value.casefold())
        if not match:
            return None
        return {"value": float(match.group(1)), "unit": match.group(2) or ""}
