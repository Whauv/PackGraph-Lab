from __future__ import annotations

from typing import TypedDict


class CostRange(TypedDict):
    low: float
    high: float
    currency: str


class MaterialRecord(TypedDict):
    material_id: str
    name: str
    category: str
    composition: str
    descriptor: str
    oxygen_barrier: int
    moisture_barrier: int
    grease_resistance: int
    seal_strength: int
    flexibility: int
    thermal_tolerance: int
    transparency: int
    food_contact_safe: bool
    recyclability_score: int
    compostability_score: int
    sustainability_score: int
    cost_range: CostRange
    substitute_material_ids: list[str]
    target_applications: list[str]
    supplier_ids: list[str]
    compliance_flags: list[str]
    compliance_state: str
    regions_available: list[str]
    source_document_ids: list[str]


class SupplierRecord(TypedDict):
    supplier_id: str
    name: str
    country: str
    certifications: list[str]
    regions_served: list[str]
    supplied_material_ids: list[str]
    lead_time_days: int
    esg_score: int
    disruption_risk_score: int


class ApplicationRecord(TypedDict):
    application_id: str
    name: str
    use_case: str
    industry_id: str
    priority: str


class RegulationRecord(TypedDict):
    regulation_id: str
    name: str
    focus: str
    effective_date: str
    active: bool


class SourceDocumentRecord(TypedDict):
    document_id: str
    title: str
    document_type: str
    material_id: str
    supplier_id: str
    issued_on: str
    provenance_score: int
    checksum: str


class NewsRecord(TypedDict):
    news_id: str
    title: str
    summary: str
    source: str
    source_type: str
    topic: str
    published_on: str
    sustainability_score: int
    compliance_state: str
    related_material_ids: list[str]
    related_supplier_ids: list[str]
    related_application_ids: list[str]


class TestReportRecord(TypedDict):
    report_id: str
    title: str
    material_id: str
    lab: str
    test_date: str
    oxygen_barrier_result: int
    seal_strength_result: int
    migration_status: str


class QuarterlySnapshot(TypedDict):
    snapshot_id: str
    supplier_id: str
    material_id: str
    quarter: str
    price_usd_per_kg: float
    price_index: float
    lead_time_days: int
    risk_score: int
    compliance_score: int
    compliance_state: str
    certification_name: str
    certification_expiration: str
    regulation_watch: str


class Relationship(TypedDict):
    type: str


class ProductRecord(TypedDict):
    product_id: str
    name: str
    application_id: str
    application_name: str
    application_use_case: str
    industry_id: str
    industry_name: str
    material_ids: list[str]
    alternate_material_ids: list[str]
    material_categories: list[str]
    supplier_ids: list[str]
    supplier_regions: list[str]
    buyer_names: list[str]
    buyer_regions: list[str]
    sustainability_score: float
    recyclability_score: float
    supply_chain_score: float
    match_score: float
    compliance_state: str
    thumbnail_tone: str


class DataBundle(TypedDict):
    materials: list[MaterialRecord]
    suppliers: list[SupplierRecord]
    applications: list[ApplicationRecord]
    material_news: list[NewsRecord]
    regulations: list[RegulationRecord]
    certifications: list[dict]
    recycling_streams: list[dict]
    regions: list[dict]
    industries: list[dict]
    source_documents: list[SourceDocumentRecord]
    test_reports: list[TestReportRecord]
    quarterly_snapshots: list[QuarterlySnapshot]
    investigations: list[dict]
    relationships: list[Relationship]
    manifest: dict
