from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any


SAFE_SUMMARY_KEYS = {
    "entity_type",
    "entity_id",
    "material_id",
    "supplier_id",
    "application_id",
    "regulation_id",
    "document_id",
    "report_id",
    "private_record_id",
    "candidate_id",
    "title",
    "name",
    "label",
    "category",
    "status",
    "score",
    "rank",
    "weighted_score",
    "confidence",
    "preview",
    "reason",
    "decision",
    "decision_source",
    "backend",
    "question",
    "intent",
    "route",
    "review_before_writeback",
}
SAFE_PROVENANCE_KEYS = {
    "provenance_id",
    "source_record_id",
    "parser_name",
    "parser_version",
    "source_kind",
    "run_id",
    "schema_version",
    "validation_error_count",
    "file_size_bytes",
}
SAFE_AUDIT_KEYS = {
    "timestamp",
    "event_type",
    "action",
    "pair_key",
    "status_code",
    "detail",
    "error",
    "path",
    "client",
    "count",
    "applied",
    "apply",
    "format",
    "include_raw_props",
    "confidence",
    "decision",
    "decision_source",
    "backend",
    "reason",
    "question",
    "review_candidate_id",
    "selected_intent",
    "selected_route",
    "selected_template",
    "tool_order",
    "writeback_policy",
}


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def hashed_path_ref(value: str | Path | None) -> str | None:
    if not value:
        return None
    return hash_text(str(value))


def safe_path_hint(value: str | Path | None) -> dict[str, Any]:
    if not value:
        return {}
    path = Path(str(value))
    return {
        "file_name": path.name,
        "path_ref": hashed_path_ref(path),
    }


def filtered_provenance(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    result = {key: payload.get(key) for key in SAFE_PROVENANCE_KEYS if payload.get(key) is not None}
    source_name = payload.get("source_name") or payload.get("source_file")
    if source_name:
        result["source_name"] = source_name
    file_hint = safe_path_hint(payload.get("file_path"))
    if file_hint:
        result.update(file_hint)
    return result


def summarize_row(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    summary = {key: payload.get(key) for key in SAFE_SUMMARY_KEYS if payload.get(key) is not None}
    if "fields" in payload and isinstance(payload["fields"], list):
        summary["fields"] = [
            {"label": field.get("label"), "value": field.get("value")}
            for field in payload["fields"][:3]
            if isinstance(field, dict)
        ]
    provenance = filtered_provenance(payload)
    if provenance:
        summary["provenance"] = provenance
    if "score_breakdown" in payload and isinstance(payload["score_breakdown"], dict):
        summary["score_breakdown"] = payload["score_breakdown"]
    return summary


def sanitize_review_payload(payload: dict[str, Any] | None, *, include_raw_props: bool = False) -> dict[str, Any]:
    payload = payload or {}
    sanitized: dict[str, Any] = {}
    for key in ("question", "intent", "route", "reason", "display_name", "submitted_by_name", "submitted_by"):
        if payload.get(key) is not None:
            sanitized[key] = payload[key]
    if payload.get("top_rows"):
        sanitized["top_rows"] = [summarize_row(item) for item in payload["top_rows"][:5] if isinstance(item, dict)]
    if payload.get("comparison"):
        comparison = payload["comparison"]
        sanitized["comparison"] = {
            key: comparison.get(key)
            for key in ("left_label", "right_label", "confidence", "decision", "reason", "score_breakdown")
            if comparison.get(key) is not None
        }
    if payload.get("score_breakdown"):
        sanitized["score_breakdown"] = payload["score_breakdown"]
    if payload.get("provenance_snippets"):
        sanitized["provenance_snippets"] = [str(item)[:240] for item in payload["provenance_snippets"][:5]]
    if payload.get("missing_evidence"):
        sanitized["missing_evidence"] = [str(item)[:240] for item in payload["missing_evidence"][:5]]
    if payload.get("entity_resolution"):
        resolution = payload["entity_resolution"]
        sanitized["entity_resolution"] = {
            "checked_rows": resolution.get("checked_rows"),
            "review_before_merge": resolution.get("review_before_merge"),
            "review_candidates": [
                {
                    key: candidate.get(key)
                    for key in ("left_label", "right_label", "confidence", "decision", "reason", "pair_key")
                    if candidate.get(key) is not None
                }
                for candidate in resolution.get("review_candidates", [])[:5]
                if isinstance(candidate, dict)
            ],
        }
    if include_raw_props:
        sanitized["raw_payload"] = payload
    return sanitized


def sanitize_audit_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    sanitized = {key: payload.get(key) for key in SAFE_AUDIT_KEYS if payload.get(key) is not None}
    if payload.get("payload") and isinstance(payload["payload"], dict):
        sanitized["payload_summary"] = sanitize_review_payload(payload["payload"])
    if payload.get("top_rows"):
        sanitized["top_rows"] = [summarize_row(item) for item in payload["top_rows"][:5] if isinstance(item, dict)]
    if payload.get("orchestration") and isinstance(payload["orchestration"], dict):
        sanitized["orchestration"] = {
            key: payload["orchestration"].get(key)
            for key in ("selected_intent", "selected_route", "selected_template", "tool_order", "writeback_policy")
            if payload["orchestration"].get(key) is not None
        }
    if payload.get("entity_resolution") and isinstance(payload["entity_resolution"], dict):
        sanitized["entity_resolution"] = sanitize_review_payload({"entity_resolution": payload["entity_resolution"]}).get("entity_resolution")
    if payload.get("destination"):
        sanitized["destination"] = safe_path_hint(payload["destination"])
    if payload.get("source"):
        sanitized["source"] = safe_path_hint(payload["source"])
    if payload.get("result") and isinstance(payload["result"], dict):
        sanitized["result_summary"] = summarize_row(payload["result"])
    if "payload_summary" not in sanitized and payload.get("payload") and isinstance(payload["payload"], dict):
        sanitized["payload_summary"] = {
            key: value
            for key, value in payload["payload"].items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
    return sanitized


def sanitize_private_record_for_graph(row: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(row)
    source_name = sanitized.get("source_name") or sanitized.get("source_file")
    if source_name:
        sanitized["source_name"] = source_name
    sanitized["file_path_ref"] = hashed_path_ref(sanitized.get("file_path"))
    for key in ("file_path", "source_url", "content_hash", "source_file"):
        sanitized.pop(key, None)
    return sanitized


def sanitize_run_report(report: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(report))
    for key in ("json_source_dir", "sqlite_path"):
        if payload.get(key):
            payload[f"{key}_hint"] = safe_path_hint(payload[key])
            payload.pop(key, None)
    artifact_paths = payload.get("artifact_paths", {})
    if isinstance(artifact_paths, dict):
        payload["artifact_paths"] = {
            name: safe_path_hint(value)
            for name, value in artifact_paths.items()
        }
    backend_mode = payload.get("backend_mode", {})
    if isinstance(backend_mode, dict) and backend_mode.get("neo4j_uri"):
        backend_mode["neo4j_uri"] = _redact_connection(backend_mode["neo4j_uri"])
    return payload


def secure_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _best_effort_restrict(path, is_dir=True)


def secure_write_json(path: Path, payload: Any) -> None:
    secure_write_text(path, json.dumps(payload, indent=2))


def secure_write_text(path: Path, text: str) -> None:
    secure_mkdir(path.parent)
    path.write_text(text, encoding="utf-8")
    _best_effort_restrict(path, is_dir=False)


def secure_append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    secure_mkdir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    _best_effort_restrict(path, is_dir=False)


def review_export_to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "candidate_id",
            "org_id",
            "candidate_type",
            "status",
            "display_name",
            "reason",
            "assigned_reviewer_id",
            "decision_state",
            "provenance_snippets",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("candidate_id", ""),
                row.get("org_id", ""),
                row.get("candidate_type", ""),
                row.get("status", ""),
                row.get("display_name", ""),
                row.get("reason", ""),
                row.get("reviewer_fields", {}).get("assigned_reviewer_id", ""),
                row.get("reviewer_fields", {}).get("decision_state", ""),
                " | ".join(row.get("provenance_snippets", [])),
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _best_effort_restrict(path: Path, *, is_dir: bool) -> None:
    try:
        os.chmod(path, 0o700 if is_dir else 0o600)
    except OSError:
        pass


def _redact_connection(uri: str) -> str:
    if "://" not in uri:
        return "***"
    scheme, rest = uri.split("://", 1)
    host = rest.split("@")[-1]
    return f"{scheme}://{host}"
