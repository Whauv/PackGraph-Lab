window.PackGraphWorkflow = {
  steps: [
    { id: "discover", label: "Discover", description: "Browse, search, and find the material worth evaluating.", targetPage: "overview" },
    { id: "evaluate", label: "Evaluate", description: "Ask the workspace for a structured recommendation.", targetPage: "overview" },
    { id: "compare", label: "Compare", description: "Shortlist and rank the real candidate set.", targetPage: "workbench" },
    { id: "validate", label: "Validate", description: "Review documents, extracted fields, and evidence gaps.", targetPage: "intelligence" },
    { id: "review", label: "Review", description: "Move the decision through assignment and sign-off.", targetPage: "intelligence" },
    { id: "export", label: "Export", description: "Package the current case for stakeholders.", targetPage: "workbench" },
  ],

  normalizeStatus(status) {
    return status === "approve" ? "review" : status || "discover";
  },

  stateFromPage(pageName) {
    const pageMap = {
      overview: { status: "discover", workflow_step: "Discover" },
      workbench: { status: "compare", workflow_step: "Compare" },
      intelligence: { status: "validate", workflow_step: "Validate" },
    };
    return pageMap[pageName] || pageMap.overview;
  },

  stateFromSection(sectionName) {
    const sectionMap = {
      dashboard: { status: "discover", workflow_step: "Discover" },
      explore: { status: "discover", workflow_step: "Discover" },
      contribute: { status: "review", workflow_step: "Review" },
      community: { status: "discover", workflow_step: "Discover" },
    };
    return sectionMap[sectionName] || sectionMap.dashboard;
  },

  stateFromResponse(response) {
    const action = response?.panel?.recommended_action || {};
    const evidenceStrength = response?.evidence_profile?.evidence_strength || "unknown";
    const missingEvidenceCount = (response?.missing_evidence || []).length;
    return {
      status: this.normalizeStatus(action.status || (response?.review_candidate ? "review" : evidenceStrength === "weak" ? "validate" : "evaluate")),
      workflow_step: action.workflow_step || (response?.review_candidate ? "Review" : evidenceStrength === "weak" ? "Validate" : "Evaluate"),
      review_state: response?.review_candidate ? "pending_human_review" : response?.review_gate?.status || "cleared",
      confidence: `${Math.round((response?.classifier?.confidence || 0) * 100)}%`,
      next_action_label: action.label || "Refine on Overview",
      next_action_target: action.target || "overview",
      next_action_reason: action.reason || "Use the current result to choose the most useful next workspace.",
      last_result_count: (response?.rows || []).length,
      missing_evidence_count: missingEvidenceCount,
      evidence_strength: evidenceStrength,
    };
  },

  caseCards(activeCase, { material = null, supplier = null, shortlist = [] } = {}) {
    const currentEntity = activeCase.focus_entity_name || material?.name || supplier?.name || "Not selected yet";
    return [
      {
        label: "Workflow",
        value: activeCase.workflow_step,
        detail: `${String(activeCase.status || "discover").replaceAll("_", " ")} | confidence ${activeCase.confidence || "pending"}`,
      },
      {
        label: "Active entity",
        value: currentEntity,
        detail: activeCase.latest_question || "Ask a question or pick a material to begin.",
      },
      {
        label: "Next move",
        value: activeCase.next_action_label || "Start in Overview",
        detail: activeCase.next_action_reason || "Search or ask a focused question to begin.",
      },
      {
        label: "Decision state",
        value: shortlist.length ? shortlist.join(", ") : "No candidates yet",
        detail: `Evidence ${activeCase.evidence_strength} | Review ${String(activeCase.review_state || "not_requested").replaceAll("_", " ")} | Missing proof ${activeCase.missing_evidence_count || 0}`,
      },
    ];
  },

  contextChips(activeCase, context = {}) {
    return [
      { label: "Case step", value: activeCase.workflow_step },
      context.materialName ? { label: "Material", value: context.materialName } : null,
      context.supplierName ? { label: "Supplier", value: context.supplierName } : null,
      activeCase.focus_entity_name ? { label: "Context", value: activeCase.focus_entity_name } : null,
      context.latestQuestion ? { label: "Question", value: context.latestQuestion } : null,
      context.latestGlobalSearch ? { label: "Search", value: context.latestGlobalSearch } : null,
      context.shortlistNames?.length ? { label: "Shortlist", value: context.shortlistNames.join(", ") } : null,
      { label: "Evidence", value: activeCase.evidence_strength },
      { label: "Review", value: String(activeCase.review_state || "not_requested").replaceAll("_", " ") },
      { label: "Next", value: activeCase.next_action_label || "Start in Overview" },
    ].filter(Boolean);
  },
};
