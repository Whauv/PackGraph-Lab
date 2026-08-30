from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated


EmailStrLike = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
PasswordStr = Annotated[str, StringConstraints(min_length=10, max_length=128)]
NameStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class ApiEnvelope(BaseModel):
    status: Literal["ok", "error"] = "ok"
    data: Any
    meta: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    error: str
    detail: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class QueryContext(BaseModel):
    entity_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64)]
    entity_id: str | None = None
    entity_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=1200)]
    options: dict[str, Any] = Field(default_factory=dict)
    context: QueryContext | None = None


class DecisionPanelItem(BaseModel):
    label: str
    detail: str = ""


class DecisionPanel(BaseModel):
    title: str
    summary: str
    recommendations: list[DecisionPanelItem] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    recommended_action: dict[str, Any] = Field(default_factory=dict)
    workflow: dict[str, Any] = Field(default_factory=dict)
    debug: dict[str, Any] = Field(default_factory=dict)


class ReviewGatePayload(BaseModel):
    status: str
    reason: str
    writeback_allowed: bool = False


class QueryAnswerPayload(BaseModel):
    question: str
    resolved_question: str
    context: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    message: str
    panel: DecisionPanel
    classifier: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    review_gate: ReviewGatePayload
    pipeline_trace: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    private_data_active: bool = False
    source: str = "graph"
    agent_state_machine: list[dict[str, Any]] = Field(default_factory=list)
    agent_tools: list[dict[str, Any]] = Field(default_factory=list)
    agent_orchestration: dict[str, Any] = Field(default_factory=dict)
    investigation_plan: dict[str, Any] = Field(default_factory=dict)
    evidence_profile: dict[str, Any] = Field(default_factory=dict)
    missing_evidence: list[str] = Field(default_factory=list)
    project_memory: dict[str, Any] = Field(default_factory=dict)
    review_candidate: dict[str, Any] | None = None
    entity_resolution: dict[str, Any] = Field(default_factory=dict)


class QueryAnswerEnvelope(BaseModel):
    status: Literal["ok"] = "ok"
    data: QueryAnswerPayload
    meta: dict[str, Any] = Field(default_factory=dict)


class ProjectMemoryPatchRequest(BaseModel):
    saved_entities: list[Any] = Field(default_factory=list)
    saved_suppliers: list[Any] = Field(default_factory=list)
    prior_questions: list[Any] = Field(default_factory=list)
    compared_entities: list[Any] = Field(default_factory=list)
    user_assumptions: list[Any] = Field(default_factory=list)
    uploaded_file_references: list[Any] = Field(default_factory=list)
    investigation_notes: list[Any] = Field(default_factory=list)


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
    owner_name: str = ""
    due_date: str | None = None
    project_status: str = "active"
    archived: bool = False
    decision_history: list[dict[str, Any]] = Field(default_factory=list)


class InvestigationUpdate(InvestigationCreate):
    status: str = "open"


class MaterialCompareRequest(BaseModel):
    material_ids: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class WorkspaceSaveRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    filters: dict[str, Any] = Field(default_factory=dict)
    selected_material_ids: list[str] = Field(default_factory=list)
    active_tab: str = "materials"


class ComponentDiscoveryRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=400)]


class LoginRequest(BaseModel):
    email: EmailStrLike
    password: PasswordStr


class RegisterRequest(BaseModel):
    name: NameStr
    email: EmailStrLike
    password: PasswordStr
    role_id: str = "explorer"


class ContributionCreate(BaseModel):
    role_id: str
    submission_type: str
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=180)]
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
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=180)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=4000)]
    related_material_id: str | None = None
    source_reference: str = ""


class CommunityReplyCreate(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=2000)]


class ReviewAssignmentRequest(BaseModel):
    reviewer_id: str


class ReviewDecisionRequest(BaseModel):
    status: Literal["approved", "rejected", "in_approval"]
    comment: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewCommentRequest(BaseModel):
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ManualReviewCandidateRequest(BaseModel):
    candidate_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=240)]
    payload: dict[str, Any] = Field(default_factory=dict)


class JobEnqueueRequest(BaseModel):
    job_type: Literal["ingest", "evaluate_entity_resolution", "import_review_decisions", "document_parse", "export_bundle"]
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)
    max_attempts: int = Field(default=3, ge=1, le=10)
    delay_seconds: int = Field(default=0, ge=0, le=3600)
