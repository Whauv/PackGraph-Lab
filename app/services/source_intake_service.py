from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class SourceIntakeService:
    """Stores user-supplied JSON/PDF sources as local, searchable workspace knowledge."""

    parser_name = "packgraph-source-intake"
    parser_version = "1.0.0"

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
        self.path = self.runtime_dir / "source_intake_records.json"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def list_sources(self, limit: int = 50, org_id: str | None = None) -> list[dict[str, Any]]:
        sources = self._read()
        if org_id:
            sources = [item for item in sources if item.get("org_id") == org_id]
        return [self._safe_source_summary(item) for item in sorted(sources, key=lambda row: row.get("uploaded_at", ""), reverse=True)[:limit]]

    def upload(
        self,
        *,
        filename: str,
        content: bytes,
        source_type: str | None = None,
        title: str | None = None,
        owner_id: str | None = None,
        org_id: str = "ORG-001",
    ) -> dict[str, Any]:
        resolved_type = self._infer_type(filename, source_type)
        text = self._decode_content(content)
        payload: Any = None
        parse_errors: list[dict[str, Any]] = []

        if resolved_type == "json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                parse_errors.append({"field": "file", "message": exc.msg, "line": exc.lineno, "column": exc.colno})
                payload = None

        if resolved_type == "pdf":
            profile = self._profile_text(text)
            extracted_records = self._extract_text_records(text)
        elif payload is not None:
            profile = self._profile_json(payload)
            extracted_records = self._extract_json_records(payload)
        else:
            profile = self._profile_text(text)
            extracted_records = self._extract_text_records(text)

        source_id = f"SRC-{uuid4().hex[:10].upper()}"
        uploaded_at = datetime.now(UTC).isoformat()
        content_hash = hashlib.sha256(content).hexdigest()
        record = {
            "source_id": source_id,
            "title": (title or filename or "Uploaded source").strip(),
            "filename": filename,
            "source_type": resolved_type,
            "uploaded_at": uploaded_at,
            "owner_id": owner_id,
            "org_id": org_id,
            "content_hash": content_hash,
            "file_size": len(content),
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "schema_version": "source-intake.v1",
            "schema_profile": profile,
            "parse_errors": parse_errors,
            "extracted_records": extracted_records[:200],
            "search_text": self._build_search_text(title or filename, profile, extracted_records),
        }
        existing_sources = self._read()
        sources = [item for item in existing_sources if item.get("content_hash") != content_hash]
        sources.append(record)
        self._write(sources)
        return {
            "source": self._safe_source_summary(record),
            "schema_profile": profile,
            "parse_errors": parse_errors,
            "extracted_records": extracted_records[:12],
            "stored_record_count": len(extracted_records[:200]),
            "deduplicated_existing_content": len(sources) < len(existing_sources),
        }

    def search(self, query: str, *, limit: int = 8, org_id: str | None = None) -> dict[str, Any]:
        terms = self._terms(query)
        rows: list[dict[str, Any]] = []
        for source in self._read():
            if org_id and source.get("org_id") != org_id:
                continue
            search_text = source.get("search_text", "").lower()
            score = sum(search_text.count(term) for term in terms)
            matched_records = []
            for extracted in source.get("extracted_records", []):
                extracted_text = extracted.get("text", "").lower()
                record_score = sum(extracted_text.count(term) for term in terms)
                if record_score:
                    matched_records.append({**extracted, "match_score": record_score})
                    score += record_score * 2
            if score:
                rows.append(
                    {
                        "entity_type": "uploaded_record",
                        "entity_id": source["source_id"],
                        "label": source["title"],
                        "source_type": source["source_type"],
                        "score": min(100, 45 + score * 8),
                        "preview": self._preview(source),
                        "schema_fields": source.get("schema_profile", {}).get("fields", [])[:10],
                        "matched_records": sorted(matched_records, key=lambda row: row.get("match_score", 0), reverse=True)[:5],
                        "provenance": {
                            "source_id": source["source_id"],
                            "filename": source.get("filename"),
                            "parser_name": source.get("parser_name"),
                            "parser_version": source.get("parser_version"),
                            "uploaded_at": source.get("uploaded_at"),
                        },
                    }
                )
        rows = sorted(rows, key=lambda row: row["score"], reverse=True)[:limit]
        return {"rows": rows, "query": {"terms": terms, "source": "source_intake"}, "source_count": len(rows)}

    def _profile_json(self, payload: Any) -> dict[str, Any]:
        counters: dict[str, Counter[str]] = defaultdict(Counter)
        counts: Counter[str] = Counter()
        max_depth = 0

        def walk(value: Any, path: str = "$", depth: int = 0) -> None:
            nonlocal max_depth
            max_depth = max(max_depth, depth)
            value_type = self._type_name(value)
            counters[path][value_type] += 1
            counts[value_type] += 1
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, f"{path}.{key}", depth + 1)
            elif isinstance(value, list):
                for child in value[:100]:
                    walk(child, f"{path}[]", depth + 1)

        walk(payload)
        fields = [
            {"path": path, "types": sorted(counter), "count": sum(counter.values())}
            for path, counter in sorted(counters.items())
            if path != "$"
        ]
        return {
            "kind": "json",
            "root_type": self._type_name(payload),
            "max_depth": max_depth,
            "type_counts": dict(counts),
            "field_count": len(fields),
            "record_count": len(self._extract_json_records(payload)),
            "fields": fields[:80],
        }

    def _profile_text(self, text: str) -> dict[str, Any]:
        words = re.findall(r"\b[\w.-]{2,}\b", text)
        dates = sorted(set(re.findall(r"\b(?:20\d{2}|19\d{2})[-/]\d{1,2}[-/]\d{1,2}\b", text)))[:12]
        identifiers = sorted(set(re.findall(r"\b(?:MAT|SUP|DOC|REP|SRC)-[\w-]+\b", text, flags=re.I)))[:20]
        return {
            "kind": "pdf" if "%PDF" in text[:20] else "text",
            "word_count": len(words),
            "line_count": len([line for line in text.splitlines() if line.strip()]),
            "detected_dates": dates,
            "detected_identifiers": identifiers,
            "field_count": 4,
            "record_count": len(self._extract_text_records(text)),
            "fields": [
                {"path": "text.lines", "types": ["string"], "count": len(text.splitlines())},
                {"path": "detected.dates", "types": ["string"], "count": len(dates)},
                {"path": "detected.identifiers", "types": ["string"], "count": len(identifiers)},
                {"path": "content.keywords", "types": ["string"], "count": len(set(words))},
            ],
        }

    def _extract_json_records(self, payload: Any) -> list[dict[str, Any]]:
        candidates = payload if isinstance(payload, list) else self._nested_dict_rows(payload)
        if isinstance(candidates, dict):
            candidates = [candidates]
        rows = []
        for index, item in enumerate(candidates[:250] if isinstance(candidates, list) else [], start=1):
            if not isinstance(item, dict):
                item = {"value": item}
            fields = {
                str(key): self._trim(value)
                for key, value in item.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
            rows.append({"record_id": f"row-{index}", "fields": fields, "text": self._record_text(fields)})
        return rows or [{"record_id": "root", "fields": {"summary": self._trim(payload)}, "text": self._trim(payload)}]

    def _nested_dict_rows(self, payload: Any) -> list[dict[str, Any]]:
        rows = []
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list) and any(isinstance(item, dict) for item in value):
                    rows.extend(item for item in value if isinstance(item, dict))
            if not rows:
                rows.append(payload)
        return rows

    def _extract_text_records(self, text: str) -> list[dict[str, Any]]:
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
        if not chunks:
            chunks = [line.strip() for line in text.splitlines() if line.strip()]
        rows = []
        for index, chunk in enumerate(chunks[:80], start=1):
            rows.append({"record_id": f"chunk-{index}", "fields": {"snippet": self._trim(chunk, 360)}, "text": self._trim(chunk, 500)})
        return rows

    def _safe_source_summary(self, source: dict[str, Any]) -> dict[str, Any]:
        profile = source.get("schema_profile", {})
        return {
            "source_id": source["source_id"],
            "title": source["title"],
            "filename": source.get("filename"),
            "source_type": source.get("source_type"),
            "uploaded_at": source.get("uploaded_at"),
            "file_size": source.get("file_size", 0),
            "parser_name": source.get("parser_name"),
            "parser_version": source.get("parser_version"),
            "field_count": profile.get("field_count", 0),
            "record_count": profile.get("record_count", 0),
            "schema_kind": profile.get("kind", profile.get("root_type", "")),
            "parse_error_count": len(source.get("parse_errors", [])),
        }

    def _infer_type(self, filename: str, source_type: str | None) -> str:
        requested = (source_type or "").strip().lower()
        if requested in {"json", "pdf"}:
            return requested
        suffix = Path(filename or "").suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix == ".pdf":
            return "pdf"
        return "text"

    def _decode_content(self, content: bytes) -> str:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    def _build_search_text(self, title: str, profile: dict[str, Any], rows: list[dict[str, Any]]) -> str:
        field_paths = " ".join(item.get("path", "") for item in profile.get("fields", []))
        row_text = " ".join(row.get("text", "") for row in rows[:80])
        return f"{title} {profile.get('kind', '')} {field_paths} {row_text}".lower()

    def _terms(self, query: str) -> list[str]:
        return [term for term in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", query.lower()) if term not in {"this", "that", "show", "find", "what", "from", "with", "for"}][:12]

    def _record_text(self, fields: dict[str, Any]) -> str:
        return " | ".join(f"{key}: {value}" for key, value in fields.items())

    def _preview(self, source: dict[str, Any]) -> str:
        rows = source.get("extracted_records", [])
        return rows[0].get("text", "")[:220] if rows else ""

    def _trim(self, value: Any, limit: int = 240) -> str:
        if value is None:
            return ""
        text = json.dumps(value, ensure_ascii=True) if isinstance(value, (dict, list)) else str(value)
        return text[:limit] + ("..." if len(text) > limit else "")

    def _type_name(self, value: Any) -> str:
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        if value is None:
            return "null"
        return type(value).__name__

    def _read(self) -> list[dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, payload: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
