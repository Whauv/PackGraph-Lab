from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, UTC
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.services.security_utils import filtered_provenance, hash_text, secure_write_json


class TransformCache:
    def __init__(self, path: Path | None = None):
        self.path = path
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                secure_write_json(self.path, {})

    def load(self) -> dict[str, Any]:
        if not self.path:
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, key: str) -> dict[str, Any] | None:
        return self.load().get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.path:
            return
        payload = self.load()
        payload[key] = value
        secure_write_json(self.path, payload)


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
        schema_version: str = "2026.08.02",
        transform_cache_path: Path | None = None,
    ):
        self.private_data_dir = private_data_dir
        self.sqlite_ingest_path = sqlite_ingest_path
        self.parser_name = parser_name
        self.parser_version = parser_version
        self.schema_version = schema_version
        self.transform_cache = TransformCache(transform_cache_path)

    def has_data(self, source_dir: Path | None = None, sqlite_path: Path | None = None) -> bool:
        json_dir = self._resolve_source_dir(source_dir)
        sqlite_file = self._resolve_sqlite_path(sqlite_path)
        has_json = bool(json_dir and any(json_dir.rglob("*.json")))
        has_sqlite = bool(sqlite_file and sqlite_file.exists())
        return has_json or has_sqlite

    def inspect_schema(
        self,
        source_dir: Path | None = None,
        sqlite_path: Path | None = None,
        *,
        max_files: int | None = None,
    ) -> dict[str, Any]:
        datasets, diagnostics = self._discover_datasets(source_dir, sqlite_path, max_files=max_files)
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
                    "schema_version": dataset["schema_version"],
                    "file_size_bytes": dataset.get("file_size_bytes"),
                    "max_nested_depth": dataset.get("max_nested_depth", 0),
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

    def ingestable_records(
        self,
        source_dir: Path | None = None,
        sqlite_path: Path | None = None,
        *,
        run_id: str | None = None,
        max_files: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = []
        datasets, _ = self._discover_datasets(source_dir, sqlite_path, max_files=max_files)
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
                row["run_id"] = run_id
                row["source_name"] = dataset.get("source_file")
                row["file_path"] = dataset.get("source_path")
                row["file_size_bytes"] = dataset.get("file_size_bytes")
                row["schema_version"] = dataset["schema_version"]
                row["validation_error_count"] = len(dataset.get("validation_errors", []))
                row["provenance"] = filtered_provenance(row)
                rows.append(row)
        return rows

    def _resolve_source_dir(self, source_dir: Path | None) -> Path | None:
        return source_dir or self.private_data_dir

    def _resolve_sqlite_path(self, sqlite_path: Path | None) -> Path | None:
        return sqlite_path or self.sqlite_ingest_path

    def _discover_datasets(
        self,
        source_dir: Path | None = None,
        sqlite_path: Path | None = None,
        *,
        max_files: int | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        datasets = []
        diagnostics = {
            "json_files_scanned": 0,
            "sqlite_tables_scanned": 0,
            "files_selected": 0,
            "invalid_sources": [],
            "duplicate_content_report": [],
            "schema_counts": {},
            "parse_errors": [],
            "validation_errors": [],
            "nested_folder_depth_summary": {},
            "file_results": [],
            "max_nested_depth": 0,
        }

        json_dir = self._resolve_source_dir(source_dir)
        json_files = sorted(json_dir.rglob("*.json")) if json_dir and json_dir.exists() else []
        if max_files is not None:
            json_files = json_files[: max(0, max_files)]
        diagnostics["files_selected"] = len(json_files)

        for path in json_files:
            diagnostics["json_files_scanned"] += 1
            path_hash = self._hash_text(str(path))
            relative_depth = max(0, len(path.relative_to(json_dir).parts) - 1) if json_dir and path.exists() else 0
            diagnostics["max_nested_depth"] = max(diagnostics["max_nested_depth"], relative_depth)
            depth_key = str(relative_depth)
            diagnostics["nested_folder_depth_summary"][depth_key] = diagnostics["nested_folder_depth_summary"].get(depth_key, 0) + 1
            cache_key = self._hash_text(f"{path}:{path.stat().st_mtime_ns}:{path.stat().st_size}")
            cached = self.transform_cache.get(cache_key)
            if cached:
                file_result = dict(cached["file_result"])
                file_result["cache_hit"] = True
                diagnostics["file_results"].append(file_result)
                diagnostics["validation_errors"].extend(cached.get("validation_errors", []))
                if cached.get("dataset"):
                    datasets.append(cached["dataset"])
                continue

            file_result = {
                "source_kind": "json",
                "path_hint": path_hash,
                "record_count": 0,
                "parse_error_count": 0,
                "validation_error_count": 0,
                "duplicate_count": 0,
                "max_nested_depth": relative_depth,
                "file_size_bytes": path.stat().st_size,
            }
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                error = {"kind": "json", "path_hint": path_hash, "error": str(exc)}
                diagnostics["invalid_sources"].append(error)
                diagnostics["parse_errors"].append(error)
                file_result["parse_error_count"] = 1
                diagnostics["file_results"].append(file_result)
                self.transform_cache.set(cache_key, {"file_result": file_result, "validation_errors": [], "dataset": None})
                continue

            record_sets = self._coerce_payload_to_record_sets(payload)
            if not record_sets:
                validation_error = {
                    "path_hint": path_hash,
                    "field": "$root",
                    "message": "JSON payload must be a dict or a list of dict records.",
                }
                diagnostics["validation_errors"].append(validation_error)
                file_result["validation_error_count"] = 1
                diagnostics["file_results"].append(file_result)
                self.transform_cache.set(cache_key, {"file_result": file_result, "validation_errors": [validation_error], "dataset": None})
                continue

            records = max(record_sets, key=len)
            validation_errors = self._validate_records(records, path_hash)
            fields = self._summarize_fields(records)
            dataset = {
                "dataset_id": f"json_dataset_{len(datasets) + 1}",
                "entity_hint": self._infer_entity_hint(records),
                "record_count": len(records),
                "fields": fields,
                "records": records,
                "source_kind": "json",
                "provenance_prefix": self._hash_text(str(path)),
                "schema_version": self.schema_version,
                "source_file": path.name,
                "source_path": str(path),
                "file_size_bytes": path.stat().st_size,
                "max_nested_depth": relative_depth,
                "validation_errors": validation_errors,
            }
            file_result["record_count"] = len(records)
            file_result["validation_error_count"] = len(validation_errors)
            diagnostics["validation_errors"].extend(validation_errors)
            diagnostics["file_results"].append(file_result)
            diagnostics["schema_counts"][dataset["entity_hint"]] = diagnostics["schema_counts"].get(dataset["entity_hint"], 0) + 1
            datasets.append(dataset)
            self.transform_cache.set(cache_key, {"file_result": file_result, "validation_errors": validation_errors, "dataset": dataset})

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
                        validation_errors = self._validate_records(records, self._hash_text(f"{sqlite_file}:{table_name}"))
                        dataset = {
                            "dataset_id": f"sqlite_{table_name}_{len(datasets) + 1}",
                            "entity_hint": self._infer_entity_hint(records),
                            "record_count": len(records),
                            "fields": self._summarize_fields(records),
                            "records": records,
                            "source_kind": "sqlite",
                            "provenance_prefix": self._hash_text(f"{sqlite_file}:{table_name}"),
                            "schema_version": self.schema_version,
                            "source_file": sqlite_file.name,
                            "source_path": f"{sqlite_file}:{table_name}",
                            "file_size_bytes": sqlite_file.stat().st_size,
                            "max_nested_depth": 0,
                            "validation_errors": validation_errors,
                        }
                        diagnostics["schema_counts"][dataset["entity_hint"]] = diagnostics["schema_counts"].get(dataset["entity_hint"], 0) + 1
                        diagnostics["validation_errors"].extend(validation_errors)
                        diagnostics["file_results"].append(
                            {
                                "source_kind": "sqlite",
                                "path_hint": self._hash_text(f"{sqlite_file}:{table_name}"),
                                "record_count": len(records),
                                "parse_error_count": 0,
                                "validation_error_count": len(validation_errors),
                                "duplicate_count": 0,
                                "max_nested_depth": 0,
                                "file_size_bytes": sqlite_file.stat().st_size,
                            }
                        )
                        datasets.append(dataset)
            except Exception as exc:
                error = {"kind": "sqlite", "path_hint": self._hash_text(str(sqlite_file)), "error": str(exc)}
                diagnostics["invalid_sources"].append(error)
                diagnostics["parse_errors"].append(error)

        duplicate_report = self._duplicate_content_report(datasets)
        diagnostics["duplicate_content_report"] = duplicate_report
        duplicate_counts = Counter()
        for duplicate in duplicate_report:
            for record in duplicate["records"]:
                duplicate_counts[(record["dataset_id"], record["record_index"])] += 1
        for result in diagnostics["file_results"]:
            path_hint = result["path_hint"]
            result["duplicate_count"] = sum(
                duplicate["occurrences"] - 1
                for duplicate in duplicate_report
                for record in duplicate["records"]
                if record["path_hint"] == path_hint
            )
        return datasets, diagnostics

    def _duplicate_content_report(self, datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for dataset in datasets:
            path_hint = self._hash_text(dataset.get("source_path", dataset["dataset_id"]))
            for index, record in enumerate(dataset["records"], start=1):
                flat = self._flatten_record(record)
                grouped[self._record_hash(flat)].append(
                    {
                        "dataset_id": dataset["dataset_id"],
                        "entity_hint": dataset["entity_hint"],
                        "source_kind": dataset["source_kind"],
                        "record_index": index,
                        "path_hint": path_hint,
                        "source_file": dataset.get("source_file"),
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
            if payload:
                record_sets.append([payload])
            for value in payload.values():
                if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                    record_sets.append(value)
            return record_sets
        return []

    def _validate_records(self, records: list[dict[str, Any]], path_hint: str) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                errors.append({"path_hint": path_hint, "record_index": index, "field": "$root", "message": "Record must be an object."})
                continue
            for key, value in record.items():
                self._validate_value(path_hint, index, key, value, errors, depth=0)
        return errors

    def _validate_value(self, path_hint: str, record_index: int, field: str, value: Any, errors: list[dict[str, Any]], *, depth: int) -> None:
        if depth > 6:
            errors.append({"path_hint": path_hint, "record_index": record_index, "field": field, "message": "Nested depth exceeds supported limit."})
            return
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                self._validate_value(path_hint, record_index, f"{field}.{nested_key}", nested_value, errors, depth=depth + 1)
            return
        if isinstance(value, list):
            for item_index, item in enumerate(value):
                if isinstance(item, (dict, list)):
                    self._validate_value(path_hint, record_index, f"{field}[{item_index}]", item, errors, depth=depth + 1)
            return
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            errors.append({"path_hint": path_hint, "record_index": record_index, "field": field, "message": f"Unsupported field type {type(value).__name__}."})

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
        return hash_text(value)

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
