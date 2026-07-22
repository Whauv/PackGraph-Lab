from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class ComponentDiscoveryService:
    def __init__(
        self,
        runtime_dir: Path,
        repository,
        fetcher: Callable[[str], dict[str, Any]] | None = None,
        timeout_seconds: int = 6,
    ) -> None:
        self.repository = repository
        self.path = runtime_dir / "discovered_components.json"
        self.timeout_seconds = timeout_seconds
        self.fetcher = fetcher or self._fetch_json

    def ensure_seed(self) -> None:
        if not self.path.exists():
            self._write_json([])

    def list_components(self) -> list[dict[str, Any]]:
        components = self._read_json([])
        return sorted(components, key=lambda item: item.get("discovered_at", ""), reverse=True)

    def get_component(self, component_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_components() if item.get("component_id") == component_id), None)

    def search_cached(self, query: str) -> list[dict[str, Any]]:
        query_lower = self._normalize_query(query)
        if not query_lower:
            return []
        return [item for item in self.list_components() if self._matches_query(item, query_lower)]

    def discover(self, query: str) -> dict[str, Any] | None:
        query_lower = self._normalize_query(query)
        if not query_lower:
            return None

        cached = self.search_cached(query_lower)
        if cached:
            return {"record": cached[0], "discovery_state": "cached"}

        web_result = self._discover_from_web(query_lower)
        if not web_result:
            return None

        records = self.list_components()
        record = {
            "component_id": f"CMP-{len(records) + 1:03d}",
            "name": web_result["name"],
            "normalized_name": self._normalize_query(web_result["name"]),
            "query": query.strip(),
            "summary": web_result["summary"],
            "component_type": web_result.get("component_type", "Web-discovered component"),
            "source_name": web_result["source_name"],
            "source_url": web_result["source_url"],
            "source_type": "web_discovery",
            "evidence": web_result.get("evidence", []),
            "aliases": web_result.get("aliases", []),
            "tags": web_result.get("tags", []),
            "related_material_ids": web_result.get("related_material_ids", []),
            "key_facts": web_result.get("key_facts", []),
            "discovered_at": datetime.now().isoformat(timespec="seconds"),
        }
        records.append(record)
        self._write_json(records)
        return {"record": record, "discovery_state": "newly_discovered"}

    def identify_input(self, query: str | None = None, filename: str | None = None, content: bytes | None = None) -> dict[str, Any] | None:
        normalized_query = self._normalize_query(query or "")
        if normalized_query:
            return {
                "query": normalized_query,
                "label": query.strip() if query else normalized_query,
                "method": "text_input",
                "confidence": 0.96,
            }

        inferred = self._infer_component_from_image(filename or "", content or b"")
        if not inferred:
            return None
        return inferred

    def discover_with_related(self, query: str | None = None, filename: str | None = None, content: bytes | None = None) -> dict[str, Any] | None:
        identification = self.identify_input(query=query, filename=filename, content=content)
        if not identification:
            return None

        resolved_query = identification["query"]
        local_results = self.repository.global_search(resolved_query)
        discovered_payload = None
        if not local_results:
            discovered_payload = self.discover(resolved_query)
            if discovered_payload:
                record = discovered_payload["record"]
                local_results = [
                    {
                        "entity_type": "component",
                        "entity_id": record["component_id"],
                        "title": record["name"],
                        "subtitle": f"{record.get('component_type', 'Web-discovered component')} | cached on {record.get('discovered_at', 'unknown date')}",
                        "meta": f"Stored from {record.get('source_name', 'web discovery')} for future lookups.",
                        "source_url": record.get("source_url", ""),
                        "discovery_state": discovered_payload["discovery_state"],
                    }
                ]

        related = self._related_payload(resolved_query, local_results, discovered_payload["record"] if discovered_payload else None)
        return {
            "identification": identification,
            "results": local_results,
            "related": related,
        }

    def _read_json(self, default: Any) -> Any:
        if not self.path.exists():
            return default
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, payload: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.lower().strip().split())

    def _matches_query(self, component: dict[str, Any], query_lower: str) -> bool:
        haystack = " ".join(
            [
                component.get("name", ""),
                component.get("normalized_name", ""),
                component.get("summary", ""),
                " ".join(component.get("aliases", [])),
                " ".join(component.get("tags", [])),
            ]
        ).lower()
        return query_lower in haystack

    def _infer_component_from_image(self, filename: str, content: bytes) -> dict[str, Any] | None:
        stem = Path(filename).stem.replace("-", " ").replace("_", " ").strip().lower()
        ascii_text = content.decode("utf-8", errors="ignore").lower()
        candidate_text = " ".join(bit for bit in [stem, ascii_text[:400]] if bit).strip()
        if not candidate_text:
            return None

        known_terms = [
            "evoh",
            "ethylene vinyl alcohol",
            "pet",
            "polyethylene terephthalate",
            "hdpe",
            "ldpe",
            "pp",
            "pla",
            "paper",
            "foil",
            "cellulose",
            "adhesive",
            "barrier layer",
            "laminate",
            "tray",
            "pouch",
            "bottle",
            "film",
        ]
        for term in known_terms:
            if term in candidate_text:
                return {
                    "query": self._normalize_query(term),
                    "label": term.title(),
                    "method": "image_filename_inference",
                    "confidence": 0.68,
                }

        tokens = [token for token in candidate_text.split() if len(token) > 2]
        if not tokens:
            return None
        inferred = " ".join(tokens[:3])
        return {
            "query": self._normalize_query(inferred),
            "label": inferred.title(),
            "method": "image_filename_inference",
            "confidence": 0.52,
        }

    def _related_payload(
        self,
        query: str,
        local_results: list[dict[str, Any]],
        discovered_record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        related_material_ids = set()
        for item in local_results:
            if item.get("entity_type") == "material":
                related_material_ids.add(item["entity_id"])

        if discovered_record:
            related_material_ids.update(discovered_record.get("related_material_ids", []))

        related_materials = [
            self.repository.material_index[item]
            for item in related_material_ids
            if item in self.repository.material_index
        ][:4]

        application_ids = []
        for material in related_materials:
            application_ids.extend(material.get("target_applications", []))
        related_applications = []
        seen_applications = set()
        for application_id in application_ids:
            if application_id in seen_applications or application_id not in self.repository.application_index:
                continue
            seen_applications.add(application_id)
            application = self.repository.application_index[application_id]
            related_applications.append(
                {
                    "application_id": application_id,
                    "name": application["name"],
                    "use_case": application["use_case"],
                }
            )
        related_components = []
        seen_components = set()
        for component in self.list_components():
            component_id = component.get("component_id")
            if not component_id or component_id in seen_components:
                continue
            if query not in self._normalize_query(component.get("name", "")) and not (
                related_material_ids and related_material_ids.intersection(set(component.get("related_material_ids", [])))
            ):
                continue
            seen_components.add(component_id)
            related_components.append(
                {
                    "component_id": component_id,
                    "name": component.get("name", "Component"),
                    "summary": component.get("summary", ""),
                }
            )

        if discovered_record and discovered_record.get("component_id") not in seen_components:
            related_components.insert(
                0,
                {
                    "component_id": discovered_record["component_id"],
                    "name": discovered_record["name"],
                    "summary": discovered_record.get("summary", ""),
                },
            )

        return {
            "materials": [
                {
                    "material_id": item["material_id"],
                    "name": item["name"],
                    "category": item["category"],
                    "compliance_state": item["compliance_state"],
                }
                for item in related_materials
            ],
            "applications": related_applications[:4],
            "components": related_components[:4],
        }

    def _discover_from_web(self, query: str) -> dict[str, Any] | None:
        for finder in (self._discover_from_wikipedia, self._discover_from_duckduckgo):
            try:
                result = finder(query)
                if result:
                    return result
            except Exception:
                continue
        return None

    def _discover_from_wikipedia(self, query: str) -> dict[str, Any] | None:
        search_url = (
            "https://en.wikipedia.org/w/api.php?"
            + urlencode(
                {
                    "action": "opensearch",
                    "search": query,
                    "limit": 1,
                    "namespace": 0,
                    "format": "json",
                }
            )
        )
        search_payload = self.fetcher(search_url)
        titles = search_payload[1] if isinstance(search_payload, list) and len(search_payload) > 1 else []
        if not titles:
            return None

        title = titles[0]
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
        summary_payload = self.fetcher(summary_url)
        extract = summary_payload.get("extract") or summary_payload.get("description")
        if not extract:
            return None

        return {
            "name": summary_payload.get("title", title),
            "summary": extract,
            "component_type": summary_payload.get("description", "Wikipedia material or component"),
            "source_name": "Wikipedia",
            "source_url": summary_payload.get("content_urls", {}).get("desktop", {}).get("page", summary_url),
            "aliases": [title],
            "tags": [summary_payload.get("type", "reference"), "Wikipedia"],
            "evidence": [extract],
            "related_material_ids": self._related_material_ids(extract),
            "key_facts": self._fact_rows(summary_payload.get("description"), extract),
        }

    def _discover_from_duckduckgo(self, query: str) -> dict[str, Any] | None:
        payload = self.fetcher(
            "https://api.duckduckgo.com/?"
            + urlencode(
                {
                    "q": query,
                    "format": "json",
                    "no_redirect": 1,
                    "no_html": 1,
                    "skip_disambig": 1,
                }
            )
        )
        abstract = payload.get("AbstractText") or payload.get("Heading")
        if not abstract:
            return None

        heading = payload.get("Heading") or query.title()
        related_topics = payload.get("RelatedTopics", [])
        evidence = [abstract]
        for topic in related_topics[:2]:
            if isinstance(topic, dict) and topic.get("Text"):
                evidence.append(topic["Text"])

        return {
            "name": heading,
            "summary": abstract,
            "component_type": payload.get("AbstractSource", "DuckDuckGo result"),
            "source_name": payload.get("AbstractSource") or "DuckDuckGo",
            "source_url": payload.get("AbstractURL") or f"https://duckduckgo.com/?q={quote(query)}",
            "aliases": [heading],
            "tags": ["DuckDuckGo", "Web discovery"],
            "evidence": evidence,
            "related_material_ids": self._related_material_ids(" ".join(evidence)),
            "key_facts": self._fact_rows(payload.get("AbstractSource"), abstract),
        }

    def _related_material_ids(self, text: str) -> list[str]:
        text_lower = text.lower()
        related = []
        for material in self.repository.materials:
            candidates = [
                material.get("name", ""),
                material.get("descriptor", ""),
                material.get("category", ""),
                material.get("composition", ""),
            ]
            haystack = " ".join(candidates).lower()
            if any(token and token in text_lower for token in haystack.split()):
                related.append(material["material_id"])
            if len(related) >= 3:
                break
        return related

    def _fact_rows(self, description: str | None, summary: str) -> list[dict[str, str]]:
        facts = []
        if description:
            facts.append({"label": "Classification", "value": description})
        facts.append({"label": "Summary", "value": summary[:220]})
        return facts

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "PackGraphLab/1.0 (+https://github.com/Whauv/PackGraph-Lab)",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
