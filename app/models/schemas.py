from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiEnvelope(BaseModel):
    status: Literal["ok", "error"] = "ok"
    data: Any
    meta: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    error: str
    detail: str | None = None


class QueryRequest(BaseModel):
    question: str
    options: dict[str, Any] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    material_id: str | None = None
    supplier_id: str | None = None
    scenario: str
    options: dict[str, Any] = Field(default_factory=dict)


class InvestigationCreate(BaseModel):
    title: str
    focus_material_id: str | None = None
    notes: str = ""
    shortlisted_material_ids: list[str] = Field(default_factory=list)
    comparison_material_ids: list[str] = Field(default_factory=list)
    decision_rationale: str = ""


class InvestigationUpdate(InvestigationCreate):
    status: str = "open"


class MaterialCompareRequest(BaseModel):
    material_ids: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class WorkspaceSaveRequest(BaseModel):
    name: str
    filters: dict[str, Any] = Field(default_factory=dict)
    selected_material_ids: list[str] = Field(default_factory=list)
    active_tab: str = "materials"


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role_id: str = "explorer"


class ContributionCreate(BaseModel):
    role_id: str
    submission_type: str
    title: str
    summary: str = ""
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    evidence_note: str = ""
    edit_request: str = ""
    proposed_links: str = ""


class ContributionReviewRequest(BaseModel):
    status: Literal["accepted", "rejected", "under_review"]
    reviewer_note: str = ""


class CommunityPostCreate(BaseModel):
    channel_id: str
    title: str
    body: str
    related_material_id: str | None = None
    source_reference: str = ""


class CommunityReplyCreate(BaseModel):
    body: str
