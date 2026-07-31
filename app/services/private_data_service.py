from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


class PrivateDataService:
    STOP_WORDS = {
        "a", "an", "and", "are", "best", "by", "do", "find", "for", "from", "get", "i", "in", "is", "list",
        "lookup", "me", "of", "on", "or", "search", "show", "tell", "the", "to", "what", "which", "with",
    }
    ENTITY_TERMS = {"product", "products", "supplier", "suppliers", "material", "materials", "location", "locations", "grade", "grades"}

    def __init__(
        self,
        private_data_dir: Path,
        sqlite_ingest_path: Path | None = None,
        *,
        parser_name: str = "packgraph-local-ingest",
        parser_version: str = "2.0",
    ):
        self.private_data_dir = private_data_dir
        self.sqlite_ingest_path = sqlite_ingest_path
        self.parser_name = parser_name
        self.parser_version = parser_version

    def has_data(self, source_dir: Path | None = None, sqlite_path: Path | None = None) -> bool:
        json_dir = self._resolve_source_dir(source_dir)
        sqlite_file = self._resolve_sqlite_path(sqlite_path)
        has_json = bool(json_dir and any(json_dir.rglob("*.json")))
        has_sqlite = bool(sqlite_file and sqlite_file.exists())
        return has_json or has_sqlite

    def inspect_schema(self, source_dir: Path | None = None, sqlite_path: Path | None = None) -> dict[str, Any]:
        datasets, diagnostics = self._discover_datasets(source_dir, sqlite_path)
        return {
            "private_data_active": bool(datasets),
            "dataset_count": len(datasets),
            "record_count": sum(dataset["record_count"] for dataset in datasets),
            "source_profile": diagnostics,
            "datasets": [
                {
                    "dataset": dataset["dataset_id"],
                    "entity_hint": dataset["entity_hint"],
                    "record_count": dataset["record_count"],
                    "fields": dataset["fields"],
                    "source_kind": dataset["source_kind"],
                    "provenance_prefix": dataset["provenance_prefix"],
                }
                for dataset in datasets
            ],
        }

    def query(self, question: str, source_dir: Path | None = None, sqlite_path: Path | None = None) -> dict[str, Any]:
        extracted = self._extract_question_parts(question)
        matches = []
        for dataset in self._discover_datasets(source_dir, sqlite_path)[0]:
            for record in dataset["records"]:
                match = self._match_record(dataset, record, extracted)
                if match:
                    matches.append(match)
        matches.sort(key=lambda item: item["score"], reverse=True)
        return {
            "private_data_active": self.has_data(source_dir, sqlite_path),
            "query": extracted,
            "rows": matches[:12],
        }

    def private_status(self) -> dict[str, Any]:
        summary = self.inspect_schema()
        return {
            "private_data_active": summary["private_data_active"],
            "dataset_count": summary["dataset_count"],
            "record_count": summary["record_count"],
        }

    def ingestable_records(self, source_dir: Path | None = None, sqlite_path: Path | None = None) -> list[dict[str, Any]]:
        rows = []
        datasets, _ = self._discover_datasets(source_dir, sqlite_path)
        for dataset in datasets:
            for index, record in enumerate(dataset["records"], start=1):
                row = self._flatten_record(record)
                source_record_id = f"{dataset['dataset_id']}:{index}"
                row["private_record_id"] = f"{dataset['dataset_id'].upper()}-{index:04d}"
                row["source_record_id"] = source_record_id
                row["entity_hint"] = dataset["entity_hint"]
                row["dataset_id"] = dataset["dataset_id"]
                row["provenance_id"] = self._hash_text(f"{dataset['provenance_prefix']}|{source_record_id}")
                row["parser_name"] = self.parser_name
                row["parser_version"] = self.parser_version
                row["source_kind"] = dataset["source_kind"]
                row["content_hash"] = self._record_hash(row)
                rows.append(row)
        return rows

    def _resolve_source_dir(self, source_dir: Path | None) -> Path | None:
        return source_dir or self.private_data_dir

    def _resolve_sqlite_path(self, sqlite_path: Path | None) -> Path | None:
        return sqlite_path or self.sqlite_ingest_path

    def _discover_datasets(self, source_dir: Path | None = None, sqlite_path: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        datasets = []
        diagnostics = {
            "json_files_scanned": 0,
            "sqlite_tables_scanned": 0,
            "invalid_sources": [],
            "duplicate_content_report": [],
        }

        json_dir = self._resolve_source_dir(source_dir)
        if json_dir and json_dir.exists():
            for path in sorted(json_dir.rglob("*.json")):
                diagnostics["json_files_scanned"] += 1
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    diagnostics["invalid_sources"].append({"kind": "json", "path_hint": self._hash_text(str(path)), "error": str(exc)})
                    continue
                for records in self._coerce_payload_to_record_sets(payload):
                    if not records:
                        continue
                    fields = self._summarize_fields(records)
                    datasets.append(
                        {
                            "dataset_id": f"json_dataset_{len(datasets) + 1}",
                            "entity_hint": self._infer_entity_hint(records),
                            "record_count": len(records),
                            "fields": fields,
                            "records": records,
                            "source_kind": "json",
                            "provenance_prefix": self._hash_text(str(path)),
                        }
                    )

        sqlite_file = self._resolve_sqlite_path(sqlite_path)
        if sqlite_file and sqlite_file.exists():
            try:
                with closing(sqlite3.connect(sqlite_file)) as connection:
                    connection.row_factory = sqlite3.Row
                    table_rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                    for table in table_rows:
                        table_name = table["name"]
                        if table_name.startswith("sqlite_"):
                            continue
                        diagnostics["sqlite_tables_scanned"] += 1
                        records = [dict(row) for row in connection.execute(f'SELECT * FROM "{table_name}"').fetchall()]
                        if not records:
                            continue
                        datasets.append(
                            {
                                "dataset_id": f"sqlite_{table_name}_{len(datasets) + 1}",
                                "entity_hint": self._infer_entity_hint(records),
                                "record_count": len(records),
                                "fields": self._summarize_fields(records),
                                "records": records,
                                "source_kind": "sqlite",
                                "provenance_prefix": self._hash_text(f"{sqlite_file}:{table_name}"),
                            }
                        )
            except Exception as exc:
                diagnostics["invalid_sources"].append({"kind": "sqlite", "path_hint": self._hash_text(str(sqlite_file)), "error": str(exc)})

        diagnostics["duplicate_content_report"] = self._duplicate_content_report(datasets)
        return datasets, diagnostics

    def _duplicate_content_report(self, datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for dataset in datasets:
            for index, record in enumerate(dataset["records"], start=1):
                flat = self._flatten_record(record)
                grouped[self._record_hash(flat)].append(
                    {
                        "dataset_id": dataset["dataset_id"],
                        "entity_hint": dataset["entity_hint"],
                        "source_kind": dataset["source_kind"],
                        "record_index": index,
                    }
                )
        return [
            {"content_hash": key, "occurrences": len(items), "records": items}
            for key, items in grouped.items()
            if len(items) > 1
        ]

    def _coerce_payload_to_record_sets(self, payload: Any) -> list[list[dict[str, Any]]]:
        if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
            return [payload]
        if isinstance(payload, dict):
            record_sets = []
            dict_records = [payload] if payload else []
            if dict_records:
                record_sets.append(dict_records)
            for value in payload.values():
                if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                    record_sets.append(value)
            return record_sets
        return []

    def _summarize_fields(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        field_types: dict[str, set[str]] = {}
        for record in records:
            for key, value in self._flatten_record(record).items():
                field_types.setdefault(key, set()).add(self._value_type(value))
        return [{"name": key, "types": sorted(types)} for key, types in sorted(field_types.items())]

    def _infer_entity_hint(self, records: list[dict[str, Any]]) -> str:
        keys = " ".join(" ".join(self._flatten_record(record).keys()) for record in records[:6]).lower()
        if "supplier" in keys or "vendor" in keys:
            return "supplier"
        if "product" in keys or "sku" in keys:
            return "product"
        if "grade" in keys:
            return "grade"
        if "material" in keys or "alloy" in keys or "polymer" in keys:
            return "material"
        if "country" in keys or "region" in keys or "location" in keys:
            return "location"
        return "record"

    def _extract_question_parts(self, question: str) -> dict[str, Any]:
        lowered = question.lower()
        entity_target = next((term.rstrip("s") for term in ["products", "suppliers", "materials", "locations", "grades"] if term in lowered), "record")
        location_match = re.search(r"\bin\s+([a-z][a-z\s\-]+?)(?:\?|$| with | for | that | where )", lowered)
        location = location_match.group(1).strip() if location_match else None
        keywords = [
            token for token in re.findall(r"[a-z0-9][a-z0-9\-/]+", lowered)
            if token not in self.STOP_WORDS and token not in self.ENTITY_TERMS and token != (location or "")
        ]
        return {"entity_target": entity_target, "location": location, "keywords": keywords[:8]}

    def _match_record(self, dataset: dict[str, Any], record: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any] | None:
        flat = self._flatten_record(record)
        haystack = " ".join(str(value).lower() for value in flat.values())
        keys = " ".join(flat.keys()).lower()
        score = 0
        if extracted["entity_target"] != "record":
            if dataset["entity_hint"] == extracted["entity_target"] or extracted["entity_target"] in keys:
                score += 3
            else:
                score -= 1
        if extracted["location"]:
            if extracted["location"] in haystack:
                score += 3
            else:
                return None
        for keyword in extracted["keywords"]:
            if keyword in haystack or keyword in keys:
                score += 2
        if extracted["keywords"] and score <= 0:
            return None
        if not extracted["keywords"] and extracted["location"] is None and extracted["entity_target"] == "record":
            return None
        label = flat.get("name") or flat.get("title") or flat.get("supplier_name") or flat.get("material_name") or flat.get("product_name") or f"{dataset['entity_hint'].title()} record"
        preview_fields = []
        for key, value in flat.items():
            if value in ("", None):
                continue
            preview_fields.append({"label": key.replace("_", " ").title(), "value": str(value)})
            if len(preview_fields) == 5:
                break
        return {
            "entity_type": dataset["entity_hint"],
            "label": str(label),
            "score": score,
            "fields": preview_fields,
        }

    def _flatten_record(self, record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, value in record.items():
            composite = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                flattened.update(self._flatten_record(value, composite))
            elif isinstance(value, list):
                flattened[composite] = ", ".join(str(item) for item in value[:8])
            else:
                flattened[composite] = value
        return flattened

    def _record_hash(self, record: dict[str, Any]) -> str:
        normalized = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _hash_text(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def _value_type(self, value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if value is None:
            return "null"
        return "string"
