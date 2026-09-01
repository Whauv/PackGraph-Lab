const state = window.PackGraphState.createDefaultState();

const REQUEST_TIMEOUT_MS = 12000;
const REQUEST_RETRY_ATTEMPTS = 1;
const DRAFT_STORAGE_KEYS = {
  contribution: "packgraph-draft-contribution",
  communityPost: "packgraph-draft-community-post",
  communityReply: "packgraph-draft-community-reply",
  investigation: "packgraph-draft-investigation",
};

function applyTheme(theme) {
  state.theme = theme;
  document.body.setAttribute("data-theme", theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  window.localStorage.setItem(window.PackGraphState.storageKeys.theme, theme);
}

function setupThemeToggle() {
  const savedTheme = window.localStorage.getItem(window.PackGraphState.storageKeys.theme);
  const preferredDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(savedTheme || (preferredDark ? "dark" : "light"));
  document.getElementById("theme-toggle").addEventListener("click", () => applyTheme(state.theme === "dark" ? "light" : "dark"));
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.sessionToken) {
    headers.Authorization = `Bearer ${state.sessionToken}`;
  }
  return headers;
}

function setSessionToken(token) {
  state.sessionToken = token || "";
  if (state.sessionToken) {
    window.localStorage.setItem(window.PackGraphState.storageKeys.sessionToken, state.sessionToken);
  } else {
    window.localStorage.removeItem(window.PackGraphState.storageKeys.sessionToken);
  }
}

function defaultActiveCase() {
  return window.PackGraphState.defaultActiveCase();
}

function loadActiveCase() {
  const stored = window.PackGraphState.loadJson(window.PackGraphState.storageKeys.activeCase, null);
  state.activeCase = stored ? { ...defaultActiveCase(), ...stored } : defaultActiveCase();
}

function persistActiveCase() {
  window.PackGraphState.saveJson(window.PackGraphState.storageKeys.activeCase, state.activeCase);
}

function loadUiWorkspaceState() {
  state.graphPinnedNodeIds = window.PackGraphState.loadJson(window.PackGraphState.storageKeys.graphPins, []);
  state.graphCollapsedTypes = window.PackGraphState.loadJson(window.PackGraphState.storageKeys.graphCollapsed, []);
}

function persistGraphUiState() {
  window.PackGraphState.saveJson(window.PackGraphState.storageKeys.graphPins, state.graphPinnedNodeIds || []);
  window.PackGraphState.saveJson(window.PackGraphState.storageKeys.graphCollapsed, state.graphCollapsedTypes || []);
}

function loadPersonalWorkspace() {
  const stored = window.PackGraphState.loadJson(window.PackGraphState.storageKeys.personalWorkspace, null);
  if (stored) {
    state.personalWorkspace = {
      bookmarks: stored.bookmarks || [],
      recent_entities: stored.recent_entities || [],
      quick_note: stored.quick_note || "",
      reminders: stored.reminders || [],
      activity_events: stored.activity_events || [],
    };
  }
}

function persistPersonalWorkspace() {
  window.PackGraphState.saveJson(window.PackGraphState.storageKeys.personalWorkspace, state.personalWorkspace);
}

function setupDraftPersistence() {
  registerDraftPersistence(DRAFT_STORAGE_KEYS.contribution, [
    "contribution-title",
    "contribution-summary",
    "contribution-evidence-note",
    "contribution-edit-request",
    "contribution-proposed-links",
    "contribution-role",
    "contribution-type",
    "contribution-entity-type",
    "contribution-entity-id",
  ]);
  registerDraftPersistence(DRAFT_STORAGE_KEYS.communityPost, [
    "community-post-title",
    "community-post-body",
    "community-source-reference",
    "community-channel-select",
    "community-related-material",
  ]);
  registerDraftPersistence(DRAFT_STORAGE_KEYS.communityReply, ["community-reply-body"]);
  registerDraftPersistence(DRAFT_STORAGE_KEYS.investigation, [
    "investigation-title",
    "investigation-project-status",
    "investigation-owner",
    "investigation-due-date",
    "investigation-notes",
    "investigation-rationale",
  ]);
}

async function syncProjectMemory(patch = {}) {
  try {
    state.projectMemory = await fetchJson("/project-memory", {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(patch),
    });
  } catch {
    // Keep the UI local-first even if memory sync is unavailable.
  }
}

function syncActiveCase(patch = {}, { syncMemory = false } = {}) {
  state.activeCase = { ...(state.activeCase || defaultActiveCase()), ...patch };
  persistActiveCase();
  renderCaseWorkspace();
  renderWorkflowMap();
  renderCrossPageContext();
  if (syncMemory) {
    syncProjectMemory({
      saved_entities: [state.activeCase.focus_material_id],
      compared_entities: state.activeCase.shortlist_material_ids || [],
      prior_questions: [state.activeCase.latest_question],
      investigation_notes: [state.activeCase.note],
      user_assumptions: [state.activeCase.workflow_step],
    });
  }
}

async function fetchJson(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const retries = Number.isFinite(options.retries) ? options.retries : REQUEST_RETRY_ATTEMPTS;
  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : REQUEST_TIMEOUT_MS;
  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(new Error("timeout")), timeoutMs);
    try {
      const response = await fetch(url, {
        ...options,
        headers: authHeaders(options.headers || {}),
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({
        status: response.ok ? "ok" : "error",
        detail: response.ok ? "" : "The server returned a non-JSON response.",
      }));
      if (!response.ok || payload.status === "error") {
        const rawMessage = payload.detail || payload.error || `Request failed with status ${response.status}`;
        const message = /traceback|exception|line \d+|file \"/i.test(rawMessage)
          ? "The request failed on the server."
          : rawMessage;
        const error = new Error(message);
        error.code = payload.error || `http_${response.status}`;
        error.status = response.status;
        throw error;
      }
      return payload.data;
    } catch (error) {
      lastError = error;
      const retryable = method === "GET" && (error.name === "AbortError" || !error.status || error.status >= 500);
      if (!retryable || attempt === retries) {
        throw new Error(error.message || "Request failed");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250 * (attempt + 1)));
    } finally {
      window.clearTimeout(timeoutId);
    }
  }
  throw lastError || new Error("Request failed");
}

function debounce(fn, wait = 250) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

function saveDraft(key, payload) {
  window.localStorage.setItem(key, JSON.stringify(payload));
}

function loadDraft(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

function clearDraft(key) {
  window.localStorage.removeItem(key);
}

function persistFormDraft(key, fields) {
  const payload = {};
  fields.forEach(({ id, property = "value" }) => {
    const element = document.getElementById(id);
    if (!element) return;
    payload[id] = element[property];
  });
  saveDraft(key, payload);
}

function restoreFormDraft(key, fields) {
  const payload = loadDraft(key);
  if (!payload) return;
  fields.forEach(({ id, property = "value" }) => {
    const element = document.getElementById(id);
    if (!element || !(id in payload)) return;
    element[property] = payload[id];
  });
}

function registerDraftPersistence(key, fieldIds, eventName = "input") {
  restoreFormDraft(key, fieldIds.map((id) => ({ id })));
  fieldIds.forEach((id) => {
    const element = document.getElementById(id);
    if (!element) return;
    element.addEventListener(eventName, () => {
      persistFormDraft(key, fieldIds.map((fieldId) => ({ id: fieldId })));
    });
  });
}

function formatTags(items, className = "tag") {
  return `<div class="tags">${items.map((item) => `<span class="${className}">${item}</span>`).join("")}</div>`;
}

function addMessage(author, text, detail = "") {
  const log = document.getElementById("chat-log");
  const message = document.createElement("div");
  const authorSlug = String(author).toLowerCase().replace(/\s+/g, "-");
  message.className = `message message-${authorSlug}`;
  message.innerHTML = `<strong>${author}</strong><div>${text}</div>${detail ? `<pre>${detail}</pre>` : ""}`;
  log.prepend(message);
}

function setChatContext(context, options = {}) {
  if (!window.PackGraphChat?.setContext) return;
  window.PackGraphChat.setContext(context, options);
  if (context) {
    syncActiveCase({
      focus_entity_type: context.entity_type || state.activeCase?.focus_entity_type || "material",
      focus_entity_id: context.entity_id || state.activeCase?.focus_entity_id || null,
      focus_entity_name: context.entity_name || state.activeCase?.focus_entity_name || "",
    });
  }
}

function buildMaterialChatContext(material) {
  if (!material) return null;
  return {
    entity_type: "material",
    entity_id: material.material_id,
    entity_name: material.name,
    metadata: {
      category: titleCase(material.category || ""),
      compliance: titleCase(material.compliance_state || ""),
      region: material.regions_available?.[0] || "",
      suppliers: material.supplier_ids?.length || 0,
    },
  };
}

function buildSupplierChatContext(supplier) {
  if (!supplier) return null;
  return {
    entity_type: "supplier",
    entity_id: supplier.supplier_id,
    entity_name: supplier.name,
    metadata: {
      region: supplier.regions_served?.[0] || supplier.primary_region || "",
      risk: supplier.disruption_risk_score ?? "",
      lead_time_days: supplier.lead_time_days ?? "",
      certifications: supplier.certifications?.length || 0,
    },
  };
}

function buildRegulationChatContext(regulation) {
  if (!regulation) return null;
  return {
    entity_type: "regulation",
    entity_id: regulation.regulation_id,
    entity_name: regulation.name,
    metadata: {
      region: regulation.region || "",
      effective_on: regulation.effective_on || "",
      focus: regulation.focus || "",
    },
  };
}

function buildExploreDetailChatContext(detail) {
  if (!detail) return null;
  const facts = {};
  (detail.facts || []).slice(0, 4).forEach((item) => {
    if (item?.label && item?.value) {
      facts[item.label.toLowerCase().replace(/\s+/g, "_")] = item.value;
    }
  });
  if (detail.focus_material_id) {
    facts.material_id = detail.focus_material_id;
  }
  return {
    entity_type: detail.entity_type || "entity",
    entity_id: detail.entity_id || "",
    entity_name: detail.title || detail.summary || "Selected entity",
    metadata: facts,
  };
}

function buildUploadedRecordChatContext(detail) {
  if (!detail) return null;
  return {
    entity_type: detail.report_id ? "report" : "document",
    entity_id: detail.document_id || detail.report_id || "",
    entity_name: detail.title || "Selected record",
    metadata: {
      document_type: detail.document_type || detail.lab || "",
      confidence: detail.confidence_summary || "",
      material_id: detail.material_id || "",
    },
  };
}

function buildComponentChatContext(label) {
  return {
    entity_type: "component",
    entity_id: "",
    entity_name: label,
    metadata: {},
  };
}

function workflowStateFromResponse(response) {
  return window.PackGraphWorkflow.stateFromResponse(response);
}

function handleChatResult(question, response) {
  state.latestQuestion = question;
  addMessage("Question", question);
  addMessage("PackGraph", response.message);
  const workflow = workflowStateFromResponse(response);
  renderStructuredAnswer({
    panel: response.panel,
    meta: {
      confidence: workflow.confidence,
      evidence_strength: workflow.evidence_strength,
      review_state: workflow.review_state,
      workflow_step: workflow.workflow_step,
      result_count: workflow.last_result_count,
      missing_evidence: workflow.missing_evidence_count,
    },
  });
  renderQueryRows(response.rows || []);
  renderExecutionDebug(response);
  syncActiveCase({
    latest_question: question,
    evidence_strength: workflow.evidence_strength,
    review_state: workflow.review_state,
    status: workflow.status,
    workflow_step: workflow.workflow_step,
    confidence: workflow.confidence,
    next_action_label: workflow.next_action_label,
    next_action_target: workflow.next_action_target,
    next_action_reason: workflow.next_action_reason,
    last_result_count: workflow.last_result_count,
    missing_evidence_count: workflow.missing_evidence_count,
    note: response.panel?.summary || "",
  }, { syncMemory: true });
}

function renderStructuredAnswer(panel) {
  if (window.PackGraphAnswerPanel) {
    window.PackGraphAnswerPanel.render(panel);
  }
  renderRecommendedNextAction(panel);
}

function renderQueryRows(rows = []) {
  const container = document.getElementById("answer-panel-rows");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No structured rows yet", "Run a question to see scored rows and recommended candidates.")
      : `<div class="table-empty">No structured rows returned yet.</div>`;
    return;
  }
  const columns = Object.keys(rows[0]).slice(0, 4);
  container.innerHTML = `
    <table class="comparison-matrix-table">
      <thead><tr>${columns.map((column) => `<th>${escapeHtml(titleCase(column))}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.slice(0, 8).map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(String(row[column] ?? ""))}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>`;
}

function renderExecutionDebug(response) {
  const container = document.getElementById("answer-panel-debug");
  if (!container) return;
  const trace = response.pipeline_trace || [];
  const classifier = response.classifier || {};
  const retrieval = response.retrieval || {};
  const review = response.review_gate || {};
  if (!trace.length && !classifier.route && !retrieval.reviewed_template) {
    container.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("Technical details stay quiet by default", "Run a question if you want to inspect routing, templates, and review-gate behavior.")
      : "";
    return;
  }
  container.innerHTML = `
    <div class="technical-details-block">
      <button type="button" id="toggle-technical-details" class="secondary technical-details-toggle">Show technical details</button>
      <div id="technical-details-content" class="debug-stack technical-details-content" hidden>
        <div class="row-card"><strong>Route</strong><p>${escapeHtml(classifier.route || "graph")} | intent ${escapeHtml(classifier.intent || "unknown")} | confidence ${escapeHtml(String(classifier.confidence ?? ""))}</p></div>
        <div class="row-card"><strong>Template</strong><p>${escapeHtml(retrieval.reviewed_template || "none")} | private matches ${escapeHtml(String(retrieval.private_matches_found ?? 0))}</p></div>
        <div class="row-card"><strong>Review gate</strong><p>${escapeHtml(review.status || "cleared")} | ${escapeHtml(review.reason || "No review note.")}</p></div>
        ${trace.map((item) => `<div class="row-card"><strong>${escapeHtml(titleCase(item.stage))}</strong><p>${escapeHtml(item.detail || "")}</p></div>`).join("")}
      </div>
    </div>`;
  document.getElementById("toggle-technical-details")?.addEventListener("click", () => {
    const content = document.getElementById("technical-details-content");
    const button = document.getElementById("toggle-technical-details");
    if (!content || !button) return;
    const hidden = content.hasAttribute("hidden");
    if (hidden) {
      content.removeAttribute("hidden");
      button.textContent = "Hide technical details";
    } else {
      content.setAttribute("hidden", "hidden");
      button.textContent = "Show technical details";
    }
  });
}

function promptDiaryGroups() {
  const groups = [
    {
      title: "Graph-safe demo prompts",
      prompts: [
        "Recommend food-safe materials for snack packaging.",
        "Show recyclable substitutes for the selected material.",
        "Trace the evidence for this material.",
        "Which materials are at risk from supplier disruption?",
      ],
    },
  ];
  if (state.privateDataStatus.private_data_active) {
    groups.push({
      title: "Private-data-safe prompts",
      prompts: [
        "Find aluminum suppliers in Germany.",
        "List products that mention grade A or premium grade.",
        "Show materials connected to France or Europe.",
        "Search suppliers with stainless or aluminum keywords.",
      ],
    });
  }
  return groups;
}

function renderPromptDiary() {
  const container = document.getElementById("prompt-diary-groups");
  if (!container) return;
  container.innerHTML = promptDiaryGroups().map((group) => `
    <div class="row-card prompt-diary-group">
      <strong>${escapeHtml(group.title)}</strong>
      <div class="prompt-row">
        ${group.prompts.map((prompt) => `<button type="button" class="mini-action" data-prompt-diary="${escapeHtml(prompt)}">${escapeHtml(prompt)}</button>`).join("")}
      </div>
    </div>
  `).join("");
  container.querySelectorAll("[data-prompt-diary]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById("question-input").value = button.dataset.promptDiary;
      document.getElementById("ask-form").requestSubmit();
    });
  });
}

function titleCase(value) {
  return String(value)
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((item) => item.charAt(0).toUpperCase() + item.slice(1))
    .join(" ");
}

function formatFilterLabel(value) {
  return value === undefined || value === null || value === "" ? "Any" : titleCase(String(value));
}

function riskClass(score) {
  if (score >= 68) return "risk-high";
  if (score >= 50) return "risk-medium";
  return "risk-low";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatEntityLabel(type) {
  const labels = {
    material: "Material",
    product: "Product",
    supplier: "Supplier",
    regulation: "Regulation",
    document: "Document",
    report: "Report",
    test_report: "Report",
    component: "Component",
  };
  return labels[type] || titleCase(type);
}

function renderTableCard(containerId, columns, rows, emptyText = "No records available.") {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = `
      <div class="table-empty">
        <span class="table-empty-illustration" aria-hidden="true"></span>
        <strong>No records yet</strong>
        <p>${escapeHtml(emptyText)}</p>
      </div>`;
    return;
  }
  container.innerHTML = `
    <table>
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            ${columns.map((column) => `<td>${column.render(row)}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>`;
}

function setStatus(id, message, tone = "info") {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = message;
  element.className = `upload-status status-${tone}`;
}

function clearStatus(id) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = "";
  element.className = "upload-status";
}

function renderSurfaceState(containerId, mode, title, text) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (mode === "loading") {
    container.innerHTML = window.PackGraphUI?.loadingState
      ? window.PackGraphUI.loadingState(title, text)
      : `<div class="table-empty"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(text)}</p></div>`;
    return;
  }
  if (mode === "error" || mode === "empty") {
    container.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState(title, text)
      : `<div class="table-empty"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(text)}</p></div>`;
  }
}

function setNotificationFilter(filter) {
  state.notificationFilter = filter || "all";
  document.querySelectorAll("[data-notification-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.notificationFilter === state.notificationFilter);
  });
  if (window.PackGraphAuthShell) {
    const visible = state.notificationFilter === "all"
      ? state.notifications
      : state.notifications.filter((item) => item.type === state.notificationFilter);
    window.PackGraphAuthShell.renderNotifications(visible);
  }
}

function openCommandCenter() {
  const panel = document.getElementById("command-center-panel");
  if (panel) panel.hidden = false;
}

function closeCommandCenter() {
  const panel = document.getElementById("command-center-panel");
  if (panel) panel.hidden = true;
}

async function runCommandCenter(queryOverride = "") {
  const input = document.getElementById("command-center-input");
  const query = queryOverride || input?.value.trim() || "";
  if (!query) {
    setStatus("command-center-status", "Type a query to search across the product.", "error");
    return;
  }
  openCommandCenter();
  setStatus("command-center-status", "Searching across PackGraph surfaces...", "info");
  state.commandCenterResults = await fetchJson(`/search/command?query=${encodeURIComponent(query)}`);
  renderCommandCenterResults();
  clearStatus("command-center-status");
}

async function openCommandResult(entityType, entityId) {
  if (entityType === "workspace") {
    await resumeWorkspace(entityId);
    setSection("dashboard");
    closeCommandCenter();
    return;
  }
  if (entityType === "investigation") {
    await resumeInvestigation(entityId);
    setPage("workbench");
    closeCommandCenter();
    return;
  }
  if (entityType === "community_post") {
    setSection("community");
    state.selectedCommunityPostId = entityId;
    await loadCommunityData();
    closeCommandCenter();
    return;
  }
  if (entityType === "scenario") {
    setPage("workbench");
    closeCommandCenter();
    return;
  }
  if (entityType === "material") {
    await openMaterial(entityId, "overview");
    closeCommandCenter();
    return;
  }
  if (entityType === "supplier") {
    await openSupplierProfile(entityId);
    closeCommandCenter();
    return;
  }
  if (entityType === "regulation") {
    await openRegulationDetail(entityId);
    closeCommandCenter();
    return;
  }
  if (entityType === "document" || entityType === "report" || entityType === "test_report") {
    setPage("workbench");
    await loadDocumentPreview(entityId);
    closeCommandCenter();
    return;
  }
  if (entityType === "product" || entityType === "component") {
    const searchInput = document.getElementById("global-search-input");
    if (searchInput) {
      searchInput.value = entityId;
    }
    setPage("overview");
    await runGlobalSearch();
    closeCommandCenter();
  }
}

function renderCommandCenterResults() {
  const container = document.getElementById("command-center-results");
  if (!container) return;
  const payload = state.commandCenterResults || {};
  const groups = [
    ["Core graph", payload.results || []],
    ["Workspaces", payload.workspaces || []],
    ["Cases", payload.investigations || []],
    ["Scenarios", payload.scenarios || []],
    ["Contributions", payload.contributions || []],
    ["Posts", payload.posts || []],
  ].filter(([, items]) => items.length);
  if (!groups.length) {
    container.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No global matches", "Try a material, supplier, regulation, scenario type, workspace, or discussion keyword.")
      : `<div class="row-card"><p>No global matches.</p></div>`;
    return;
  }
  container.innerHTML = groups.map(([title, items]) => `
    <div class="command-center-group">
      <h4>${escapeHtml(title)}</h4>
      ${window.PackGraphUI?.tableList
        ? window.PackGraphUI.tableList(
            items.map((item) => `
              <button type="button" class="saved-search-card command-center-result ui-table-row" data-command-open="${escapeHtml(item.entity_type)}::${escapeHtml(item.entity_id)}">
                <div class="ui-table-row-main">
                  <span class="section-label">${escapeHtml(item.entity_type || "record")}</span>
                  <strong>${escapeHtml(item.title || item.label || item.entity_id)}</strong>
                </div>
                <small class="ui-table-row-meta">${escapeHtml(item.subtitle || item.entity_type || "")}</small>
              </button>`),
            "No matches",
            `No ${escapeHtml(title.toLowerCase())} matched this search.`,
          )
        : `<div class="card-list compact-list">
            ${items.map((item) => `
              <button type="button" class="row-card saved-search-card" data-command-open="${escapeHtml(item.entity_type)}::${escapeHtml(item.entity_id)}">
                <strong>${escapeHtml(item.title)}</strong>
                <small>${escapeHtml(item.subtitle || item.entity_type || "")}</small>
              </button>`).join("")}
          </div>`}
    </div>
  `).join("");
  container.querySelectorAll("[data-command-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      const [entityType, entityId] = button.dataset.commandOpen.split("::");
      await openCommandResult(entityType, entityId);
    });
  });
}

function renderCaseWorkspace() {
  const container = document.getElementById("case-workspace-panel");
  if (!container) return;
  const activeCase = state.activeCase || defaultActiveCase();
  const material = state.materials.find((item) => item.material_id === activeCase.focus_material_id);
  const supplier = state.suppliers.find((item) => item.supplier_id === activeCase.focus_supplier_id);
  const shortlist = (activeCase.shortlist_material_ids || [])
    .map((id) => state.materials.find((item) => item.material_id === id)?.name)
    .filter(Boolean);
  container.innerHTML = window.PackGraphWorkflow.caseCards(activeCase, { material, supplier, shortlist })
    .map((card) => `
      <div class="status-card case-workspace-card">
        <span>${escapeHtml(card.label)}</span>
        <strong>${escapeHtml(card.value)}</strong>
        <small>${escapeHtml(card.detail)}</small>
      </div>`).join("");
  renderActiveCaseActions();
}

function activeCaseContext() {
  const activeCase = state.activeCase || defaultActiveCase();
  const material = state.materials.find((item) => item.material_id === (activeCase.focus_material_id || state.selectedMaterialId));
  const supplier = state.suppliers.find((item) => item.supplier_id === activeCase.focus_supplier_id || item.supplier_id === state.latestSupplierId);
  return {
    entity_type: activeCase.focus_entity_type || (supplier ? "supplier" : "material"),
    entity_id: activeCase.focus_entity_id || supplier?.supplier_id || material?.material_id || state.selectedMaterialId || "",
    entity_name: activeCase.focus_entity_name || supplier?.name || material?.name || "Current case",
    metadata: {
      material_id: material?.material_id || state.selectedMaterialId || "",
      supplier_id: supplier?.supplier_id || "",
      workflow_step: activeCase.workflow_step,
      evidence_strength: activeCase.evidence_strength,
      review_state: activeCase.review_state,
    },
  };
}

function renderActiveCaseActions() {
  const container = document.getElementById("active-case-actions");
  if (!container || !window.PackGraphEntityActions) return;
  window.PackGraphEntityActions.render(container, activeCaseContext(), {
    shortlist: async (context) => {
      const materialId = context.metadata?.material_id || state.selectedMaterialId;
      addMaterialToShortlist(materialId);
      setStatus("case-status", "Added the active material to the shortlist.", "success");
    },
    compare: async (context) => {
      const materialId = context.metadata?.material_id || state.selectedMaterialId;
      addMaterialToShortlist(materialId);
      setPage("workbench");
      await runComparison();
    },
    graph: async (context) => {
      const materialId = context.metadata?.material_id || state.selectedMaterialId;
      await openMaterial(materialId, "intelligence");
    },
    evidence: async () => {
      setPage("workbench");
      await loadProvenance();
    },
    scenario: async () => {
      setPage("workbench");
      document.getElementById("scenario-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    review: async (context) => {
      await sendEntityToReview(
        `${context.entity_type || "entity"}_decision`,
        `Review requested for ${context.entity_name || "current entity"}.`,
        {
          entity_id: context.entity_id,
          entity_type: context.entity_type,
          display_name: context.entity_name,
          provenance_snippets: [`Active case step: ${context.metadata?.workflow_step || "Discover"}`],
        }
      );
    },
    export: (context) => {
      const materialId = context.metadata?.material_id || state.selectedMaterialId;
      window.open(`/exports/executive-summary.pdf?material_id=${encodeURIComponent(materialId)}`, "_blank", "noopener");
    },
  });
}

function roleDashboardProfile() {
  const roleId = state.currentUser?.role_id || "explorer";
  const profiles = {
    admin: {
      label: "Operations overview",
      summary: "Start from workflow health, review backlog, and graph activity before you inspect a single case.",
      focus: "Review backlog and ingest health",
      next: "Open Workbench review queue",
    },
    compliance: {
      label: "Compliance workspace",
      summary: "Start from regulations, evidence gaps, and approvals before you move into supplier or material comparisons.",
      focus: "Regulation pressure and evidence gaps",
      next: "Inspect approval and evidence surfaces",
    },
    procurement: {
      label: "Procurement workspace",
      summary: "Start from supplier exposure, lead time, and alternates before you commit to a material path.",
      focus: "Supplier stability and cost pressure",
      next: "Compare fallback suppliers and substitutes",
    },
    strategist: {
      label: "Packaging strategy workspace",
      summary: "Start from fit, shortlist quality, and tradeoffs before you move into final approval.",
      focus: "Candidate quality and portfolio fit",
      next: "Use Workbench for direct comparison",
    },
    fellow: {
      label: "R&D workspace",
      summary: "Start from technical fit, document evidence, and substitution logic before you lock a recommendation.",
      focus: "Performance and evidence strength",
      next: "Open Intelligence for graph and provenance",
    },
    explorer: {
      label: "Explorer workspace",
      summary: "Start from search and discovery, then promote only promising candidates into deeper decision work.",
      focus: "Search, shortlist, and learn",
      next: "Use Overview and Explore together",
    },
  };
  return profiles[roleId] || profiles.explorer;
}

function renderRoleDashboard() {
  state.roleDashboardProfile = roleDashboardProfile();
  const panel = document.getElementById("role-dashboard-panel");
  const heroNote = document.getElementById("overview-selected-material-note");
  const onboarding = document.querySelector("#overview-onboarding .onboarding-hint-copy p");
  const workflowSummary = document.getElementById("workflow-summary");
  if (panel) {
    const profile = state.roleDashboardProfile;
    const roleTitle = state.currentUser?.role_title || profile.label;
    panel.innerHTML = `
      <div class="panel-header compact-panel-header">
        <div>
          <p class="eyebrow">Role dashboard</p>
          <h3>${escapeHtml(roleTitle)}</h3>
        </div>
        <div class="panel-kicker">${escapeHtml(profile.next)}</div>
      </div>
      <p class="panel-helper">${escapeHtml(profile.summary)}</p>
      <div class="role-dashboard-grid">
        <div class="status-card role-dashboard-card">
          <span>Focus</span>
          <strong>${escapeHtml(profile.focus)}</strong>
        </div>
        <div class="status-card role-dashboard-card">
          <span>Review backlog</span>
          <strong>${escapeHtml(String(state.reviewSummary?.pending || 0))}</strong>
        </div>
        <div class="status-card role-dashboard-card">
          <span>Open signals</span>
          <strong>${escapeHtml(String((state.notifications || []).length))}</strong>
        </div>
      </div>`;
  }
  if (heroNote && state.selectedMaterialDetail) {
    heroNote.textContent = `${state.roleDashboardProfile.label}. ${state.roleDashboardProfile.summary}`;
  }
  if (onboarding) {
    onboarding.textContent = `${state.roleDashboardProfile.summary} Focus on ${state.roleDashboardProfile.focus.toLowerCase()} first.`;
  }
  if (workflowSummary) {
    workflowSummary.textContent = `${state.roleDashboardProfile.focus}. Next: ${state.roleDashboardProfile.next}.`;
  }
}

function pushRecentEntity(entity) {
  if (!entity?.id || !entity?.label) return;
  state.personalWorkspace.recent_entities = [
    entity,
    ...(state.personalWorkspace.recent_entities || []).filter((item) => item.id !== entity.id),
  ].slice(0, 8);
  persistPersonalWorkspace();
  renderPersonalWorkspace();
}

function addBookmark(entity) {
  if (!entity?.id || !entity?.label) return;
  if (state.personalWorkspace.bookmarks.some((item) => item.id === entity.id)) return;
  state.personalWorkspace.bookmarks = [entity, ...(state.personalWorkspace.bookmarks || [])].slice(0, 10);
  persistPersonalWorkspace();
  renderPersonalWorkspace();
}

function renderPersonalWorkspace() {
  const container = document.getElementById("productivity-panel");
  const note = document.getElementById("productivity-note");
  if (!container) return;
  if (note) note.value = state.personalWorkspace.quick_note || "";
  const bookmarks = state.personalWorkspace.bookmarks || [];
  const recent = state.personalWorkspace.recent_entities || [];
  const reminders = state.personalWorkspace.reminders || [];
  container.innerHTML = `
    <div class="row-card">
      <strong>Bookmarks</strong>
      <div class="tags">${bookmarks.length ? bookmarks.map((item) => `<span class="tag">${escapeHtml(item.label)}</span>`).join("") : `<span class="tag">No bookmarks</span>`}</div>
    </div>
    <div class="row-card">
      <strong>Recently viewed</strong>
      <div class="tags">${recent.length ? recent.map((item) => `<span class="tag">${escapeHtml(item.label)}</span>`).join("") : `<span class="tag">No recent entities</span>`}</div>
    </div>
    <div class="row-card">
      <strong>Reminders</strong>
      <div class="card-list compact-list">${reminders.length ? reminders.map((item, index) => `<div class="row-card"><p>${escapeHtml(item)}</p><button type="button" class="mini-action secondary" data-remove-reminder="${index}">Done</button></div>`).join("") : `<div class="row-card"><p>No reminders yet.</p></div>`}</div>
    </div>`;
  container.querySelectorAll("[data-remove-reminder]").forEach((button) => {
    button.addEventListener("click", () => {
      state.personalWorkspace.reminders.splice(Number(button.dataset.removeReminder), 1);
      persistPersonalWorkspace();
      renderPersonalWorkspace();
    });
  });
}

function renderActivityTimeline() {
  const container = document.getElementById("activity-timeline");
  if (!container) return;
  const timeline = [
    ...(state.personalWorkspace.activity_events || []).slice(0, 5),
    ...(state.notifications || []).slice(0, 4).map((item) => ({ title: item.title, detail: item.detail, type: item.type })),
    ...(state.scenarioHistory || []).slice(0, 3).map((item) => ({ title: titleCase(item.scenario_type), detail: item.after?.summary || "Scenario completed", type: "scenario" })),
    ...(state.investigations || []).slice(0, 3).map((item) => ({ title: item.title, detail: `${item.project_status || item.status} | due ${item.due_date || "not set"}`, type: "case" })),
  ].slice(0, 8);
  container.innerHTML = timeline.length
    ? timeline.map((item) => `<div class="row-card"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.type)}</small><p>${escapeHtml(item.detail)}</p></div>`).join("")
    : `<div class="row-card"><p>No activity yet.</p></div>`;
}

function addActivityEvent(title, detail, type = "activity") {
  state.personalWorkspace.activity_events = [
    { title, detail, type, at: new Date().toISOString() },
    ...(state.personalWorkspace.activity_events || []),
  ].slice(0, 20);
  persistPersonalWorkspace();
  renderActivityTimeline();
}

function renderOperationsDashboard() {
  const cards = document.getElementById("operations-health-cards");
  const latency = document.getElementById("operations-latency-list");
  const artifacts = document.getElementById("operations-artifact-list");
  if (!cards || !latency || !artifacts) return;
  const dashboard = state.operationsDashboard || {};
  const healthCards = dashboard.health_cards || [];
  cards.innerHTML = healthCards.length
    ? healthCards.map((item) => `
      <div class="metric operations-health-card">
        <div class="value">${escapeHtml(String(item.value))}</div>
        <div>${escapeHtml(item.label)}</div>
        ${window.PackGraphUI?.tonePill ? window.PackGraphUI.tonePill(item.tone || "neutral", item.tone || "neutral") : ""}
      </div>`).join("")
    : (window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No operations signal yet", "Use the app to generate request, graph, review, and job telemetry.")
      : `<div class="table-empty">No operations signal yet.</div>`);
  latency.innerHTML = (dashboard.query_latency || []).length
    ? dashboard.query_latency.map((item) => `
      <div class="row-card">
        <strong>${escapeHtml(item.path)}</strong>
        <small>${escapeHtml(String(item.count || 0))} requests | avg ${escapeHtml(String(item.avg || 0))} ms | max ${escapeHtml(String(item.max || 0))} ms</small>
      </div>`).join("")
    : (window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No latency samples", "Route timing appears here after requests are recorded.")
      : `<div class="row-card"><p>No latency samples.</p></div>`);
  const runtime = dashboard.runtime_artifacts || {};
  const locations = dashboard.artifact_locations || {};
  artifacts.innerHTML = [
    ["Runtime files", runtime.runtime_files ?? 0, locations.runtime],
    ["Staging files", runtime.staging_files ?? 0, locations.staging],
    ["Report files", runtime.report_files ?? 0, locations.reports],
  ].map(([label, value, path]) => `
    <div class="row-card">
      <strong>${escapeHtml(String(value))} ${escapeHtml(label)}</strong>
      <small>${escapeHtml(path || "local runtime")}</small>
    </div>`).join("");
}

async function loadOperationsDashboard() {
  try {
    state.operationsDashboard = await fetchJson("/operations/dashboard");
  } catch {
    state.operationsDashboard = null;
  }
  renderOperationsDashboard();
}

function workflowSteps() {
  return window.PackGraphWorkflow.steps;
}

function renderWorkflowMap() {
  const container = document.getElementById("workflow-map");
  const summary = document.getElementById("workflow-summary");
  if (!container) return;
  const activeStep = window.PackGraphWorkflow.normalizeStatus((state.activeCase?.status || "discover").toLowerCase());
  const stepIndex = workflowSteps().findIndex((step) => step.id === activeStep);
  container.innerHTML = workflowSteps().map((step, index) => `
    <button type="button" class="workflow-map-step workflow-map-step-button ${index === stepIndex ? "active" : index < stepIndex ? "complete" : ""}" data-workflow-target="${step.id}">
      <span>${escapeHtml(step.label)}</span>
      <strong>${index + 1}</strong>
      <small>${escapeHtml(step.description)}</small>
    </button>`).join("");
  if (summary) {
    summary.textContent = state.activeCase?.next_action_reason
      ? `${state.activeCase.workflow_step}: ${state.activeCase.next_action_reason}`
      : state.activeCase?.latest_question
        ? `${state.activeCase.workflow_step}: ${state.activeCase.latest_question}`
        : "Start in Overview, then move forward only when the answer is strong enough.";
  }
  container.querySelectorAll("[data-workflow-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.workflowTarget;
      const step = workflowSteps().find((item) => item.id === target);
      setPage(step?.targetPage || "overview");
    });
  });
}

function setupOverviewOnboardingHint() {
  const panel = document.getElementById("overview-onboarding");
  const dismissButton = document.getElementById("dismiss-overview-hint");
  if (!panel || !dismissButton) return;

  const storageKey = "packgraph-overview-hint-dismissed";
  if (window.localStorage.getItem(storageKey) === "true") {
    panel.hidden = true;
  }

  dismissButton.addEventListener("click", () => {
    panel.hidden = true;
    window.localStorage.setItem(storageKey, "true");
  });
}

function updateGraphContextBar(graph, edges) {
  const container = document.getElementById("graph-context-bar");
  if (!container) return;
  const selectedNode = graph.nodes.find((node) => node.id === state.selectedGraphNodeId) || graph.nodes[0];
  const relationshipSet = [...new Set(edges.map((edge) => titleCase(edge.type)))];
  container.innerHTML = `
    <div class="graph-context-item">
      <span>Active node</span>
      <strong>${escapeHtml(selectedNode?.label || "None selected")}</strong>
    </div>
    <div class="graph-context-item">
      <span>Branch set</span>
      <strong>${escapeHtml(state.graphPreset === "full" ? "Full graph" : titleCase(state.graphPreset))}</strong>
    </div>
    <div class="graph-context-item">
      <span>Relationship filter</span>
      <strong>${escapeHtml(state.graphFilter === "all" ? "All relationships" : titleCase(state.graphFilter))}</strong>
    </div>
    <div class="graph-context-item">
      <span>Visible relationships</span>
      <strong>${escapeHtml(relationshipSet.length ? relationshipSet.join(", ") : "None")}</strong>
    </div>
    <div class="graph-context-item">
      <span>Pinned / collapsed</span>
      <strong>${escapeHtml(`${state.graphPinnedNodeIds.length} pinned | ${state.graphCollapsedTypes.length} collapsed`)}</strong>
    </div>`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function applyGraphZoom() {
  const viewport = document.getElementById("graph-viewport");
  const zoomLabel = document.getElementById("graph-zoom-level");
  if (viewport) {
    viewport.style.transform = `translate(${state.graphPan.x}px, ${state.graphPan.y}px) scale(${state.graphZoom})`;
  }
  if (zoomLabel) {
    zoomLabel.textContent = `${Math.round(state.graphZoom * 100)}%`;
  }
}

function relationshipPriority(type) {
  const order = {
    SUPPLIED_BY: 1,
    SUPPLIES: 1,
    TARGETS_APPLICATION: 2,
    HAS_DOCUMENT: 3,
    REVIEWED_UNDER: 4,
    RECYCLES_INTO: 5,
    SUBSTITUTES_WITH: 6,
  };
  return order[type] || 99;
}

function relationshipLane(type) {
  const lanes = {
    TARGETS_APPLICATION: "applications",
    HAS_DOCUMENT: "documents",
    RECYCLES_INTO: "recycling",
    SUPPLIED_BY: "suppliers",
    SUPPLIES: "suppliers",
    SUBSTITUTES_WITH: "substitutes",
    REVIEWED_UNDER: "regulations",
  };
  return lanes[type] || "related";
}

function centerNodeAnchorOffset(type) {
  const offsets = {
    TARGETS_APPLICATION: -28,
    HAS_DOCUMENT: -4,
    RECYCLES_INTO: 24,
    SUPPLIED_BY: -20,
    SUBSTITUTES_WITH: 16,
    REVIEWED_UNDER: 34,
  };
  return offsets[type] || 0;
}

function graphEdgeAnchors(source, target) {
  const direction = target.x >= source.x ? 1 : -1;
  const edgeInset = 1;

  return {
    source: {
      x: source.x + (source.halfWidth - edgeInset) * direction,
      y: source.y,
    },
    target: {
      x: target.x - (target.halfWidth - edgeInset) * direction,
      y: target.y,
    },
  };
}

function measureGraphNodes(positions) {
  const metrics = {};
  document.querySelectorAll(".graph-node").forEach((node) => {
    const nodeId = node.dataset.nodeId;
    const position = positions[nodeId];
    if (!position) return;
    metrics[nodeId] = {
      x: position.x,
      y: position.y,
      halfWidth: node.offsetWidth / 2,
      halfHeight: node.offsetHeight / 2,
    };
  });
  return metrics;
}

function centeredStackPositions(count, centerY, gap, minY, maxY) {
  if (!count) return [];
  const totalHeight = gap * (count - 1);
  let startY = centerY - totalHeight / 2;
  startY = clamp(startY, minY, Math.max(minY, maxY - totalHeight));
  return Array.from({ length: count }, (_, index) => startY + index * gap);
}

function distributedPositions(count, start, end) {
  if (!count) return [];
  if (count === 1) return [(start + end) / 2];
  const span = end - start;
  return Array.from({ length: count }, (_, index) => start + (span * index) / (count - 1));
}

function graphGroupConfig(group) {
  const configs = {
    applications: { axis: "left", nodeX: 162, branchX: 360, startY: 118, endY: 228, label: "Targets application", labelY: 82 },
    documents: { axis: "left", nodeX: 162, branchX: 344, startY: 316, endY: 404, label: "Has document", labelY: 286 },
    recycling: { axis: "left", nodeX: 162, branchX: 328, startY: 486, endY: 548, label: "Recycles into", labelY: 458 },
    suppliers: { axis: "right", nodeX: 838, branchX: 642, startY: 118, endY: 228, label: "Supplied by", labelY: 82 },
    substitutes: { axis: "right", nodeX: 838, branchX: 666, startY: 332, endY: 560, label: "Substitutes with", labelY: 304 },
    regulations: { axis: "bottom", nodeY: 560, branchY: 472, centerX: 500, gap: 180, label: "Reviewed under" },
    related: { axis: "right", nodeX: 838, branchX: 666, startY: 332, endY: 560, label: "Related", labelY: 304 },
  };
  return configs[group] || configs.related;
}

function routeVerticalGroupPaths(sourceAnchor, branchX, targetAnchors) {
  const topY = Math.min(sourceAnchor.y, ...targetAnchors.map((anchor) => anchor.y));
  const bottomY = Math.max(sourceAnchor.y, ...targetAnchors.map((anchor) => anchor.y));
  return [
    `M ${sourceAnchor.x} ${sourceAnchor.y} L ${branchX} ${sourceAnchor.y} L ${branchX} ${topY} L ${branchX} ${bottomY}`,
    ...targetAnchors.map((anchor) => `M ${branchX} ${anchor.y} L ${anchor.x} ${anchor.y}`),
  ];
}

function routeBottomGroupPaths(sourceAnchor, branchY, targetAnchors) {
  const leftX = Math.min(sourceAnchor.x, ...targetAnchors.map((anchor) => anchor.x));
  const rightX = Math.max(sourceAnchor.x, ...targetAnchors.map((anchor) => anchor.x));
  return [
    `M ${sourceAnchor.x} ${sourceAnchor.y} L ${sourceAnchor.x} ${branchY} L ${leftX} ${branchY} L ${rightX} ${branchY}`,
    ...targetAnchors.map((anchor) => `M ${anchor.x} ${branchY} L ${anchor.x} ${anchor.y}`),
  ];
}

function normalizeGraphEdges(graph, selectedNodeId) {
  const visibleNodeIds = new Set(graph.nodes.map((node) => node.id));
  const normalized = [];
  const seen = new Set();
  const presetTypes = {
    full: null,
    supply: new Set(["SUPPLIED_BY", "SUPPLIES", "SUBSTITUTES_WITH"]),
    evidence: new Set(["HAS_DOCUMENT"]),
    compliance: new Set(["REVIEWED_UNDER", "SUBSTITUTES_WITH"]),
  };
  const allowedByPreset = presetTypes[state.graphPreset] || null;

  graph.edges.forEach((edge) => {
    if (edge.source !== selectedNodeId && edge.target !== selectedNodeId) return;
    if (state.graphFilter !== "all" && edge.type !== state.graphFilter && !(state.graphFilter === "SUPPLIED_BY" && edge.type === "SUPPLIES")) return;
    if (allowedByPreset && !allowedByPreset.has(edge.type) && !(edge.type === "SUPPLIES" && allowedByPreset.has("SUPPLIED_BY"))) return;
    const neighborId = edge.source === selectedNodeId ? edge.target : edge.source;
    if (!visibleNodeIds.has(neighborId)) return;

    let type = edge.type;
    if (type === "SUPPLIES") {
      type = "SUPPLIED_BY";
    }
    if (state.graphCollapsedTypes.includes(type) && !state.graphPinnedNodeIds.includes(neighborId)) {
      return;
    }

    const key = `${type}:${neighborId}`;
    if (seen.has(key)) return;
    seen.add(key);
    normalized.push({
      source: selectedNodeId,
      target: neighborId,
      type,
    });
  });

  return normalized.sort((a, b) => relationshipPriority(a.type) - relationshipPriority(b.type) || a.target.localeCompare(b.target));
}

function layoutGraphNodes(nodes, edges, selectedNodeId) {
  const width = 1000;
  const height = 640;
  const centerX = width / 2;
  const centerY = height / 2;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || nodes[0];
  const positions = {};
  const branches = [];

  if (selectedNode) {
    positions[selectedNode.id] = { x: centerX, y: centerY };
  }

  const connectedEdges = edges
    .filter((edge) => edge.source === selectedNode?.id || edge.target === selectedNode?.id)
    .sort((a, b) => relationshipPriority(a.type) - relationshipPriority(b.type) || a.type.localeCompare(b.type));

  const grouped = connectedEdges.reduce((acc, edge) => {
    const type = edge.type;
    const neighborId = edge.source === selectedNode?.id ? edge.target : edge.source;
    const node = nodes.find((item) => item.id === neighborId);
    if (!node) return acc;
    if (!acc[type]) acc[type] = [];
    acc[type].push(node);
    return acc;
  }, {});

  Object.entries(grouped).forEach(([type, groupNodes]) => {
    const group = relationshipLane(type);
    const config = graphGroupConfig(group);
    const sortedNodes = [...groupNodes].sort((a, b) => a.label.localeCompare(b.label));

    if (config.axis === "bottom") {
      const xs = centeredStackPositions(sortedNodes.length, config.centerX, config.gap, 172, width - 172);
      branches.push({
        type,
        group,
        axis: config.axis,
        label: config.label,
        branchY: config.branchY,
        textX: centerX,
        textY: config.branchY - 14,
        textAnchor: "middle",
      });
      sortedNodes.forEach((node, index) => {
        positions[node.id] = {
          x: xs[index],
          y: config.nodeY,
        };
      });
      return;
    }

    const ys = distributedPositions(sortedNodes.length, config.startY, config.endY);
    const textX = config.axis === "left" ? config.branchX - 20 : config.branchX + 20;
    branches.push({
      type,
      group,
      axis: config.axis,
      label: config.label,
      branchX: config.branchX,
      textX,
      textY: config.labelY ?? ys[0] - 24,
      textAnchor: config.axis === "left" ? "end" : "start",
    });
    sortedNodes.forEach((node, index) => {
      positions[node.id] = {
        x: config.nodeX,
        y: ys[index],
      };
    });
  });

  return { positions, branches };
}

function renderGraphCanvas(graph) {
  const graphRootId = state.graphIsolateSelection ? state.selectedGraphNodeId : state.selectedMaterialId;
  const normalizedEdges = normalizeGraphEdges(graph, graphRootId);
  const visibleIds = new Set([graphRootId, ...normalizedEdges.flatMap((edge) => [edge.source, edge.target])]);
  const visibleNodes = graph.nodes.filter((node) => visibleIds.has(node.id));
  const { positions, branches } = layoutGraphNodes(visibleNodes, normalizedEdges, graphRootId);
  const edgesSvg = document.getElementById("graph-edges");
  const nodesLayer = document.getElementById("graph-nodes-layer");

  nodesLayer.innerHTML = visibleNodes.map((node) => {
    const position = positions[node.id];
    if (!position) return "";
    return `
      <button
        type="button"
        class="graph-node graph-node-${escapeHtml(node.type)}${node.id === state.selectedGraphNodeId ? " active" : ""}${node.id === graphRootId ? " center" : ""}"
        data-node-id="${node.id}"
        style="left:${position.x}px; top:${position.y}px;"
      >
        <span>${escapeHtml(titleCase(node.type))}</span>
        <strong>${escapeHtml(node.label)}</strong>
      </button>`;
  }).join("");

  const nodeMetrics = measureGraphNodes(positions);
  const branchByType = Object.fromEntries(branches.map((branch) => [branch.type, branch]));
  const edgesByType = normalizedEdges.reduce((acc, edge) => {
    if (!acc[edge.type]) acc[edge.type] = [];
    acc[edge.type].push(edge);
    return acc;
  }, {});

  edgesSvg.innerHTML = [
    ...branches.map((branch) => `<text class="graph-branch-label" x="${branch.textX}" y="${branch.textY}" text-anchor="${branch.textAnchor}">${escapeHtml(branch.label)}</text>`),
    ...Object.entries(edgesByType).flatMap(([type, branchEdges]) => {
      const branch = branchByType[type];
      if (!branch || !branchEdges.length) return [];

      const source = nodeMetrics[branchEdges[0].source];
      if (!source) return [];

      const targetAnchors = branchEdges
        .map((edge) => {
          const target = nodeMetrics[edge.target];
          if (!target) return null;
          return graphEdgeAnchors(source, target).target;
        })
        .filter(Boolean)
        .sort((a, b) => a.y - b.y);

      if (!targetAnchors.length) return [];

      const firstTarget = nodeMetrics[branchEdges[0].target];
      if (!firstTarget) return [];
      const sourceMetric = {
        ...source,
        y: source.y + centerNodeAnchorOffset(type),
      };
      const sourceAnchor = graphEdgeAnchors(sourceMetric, firstTarget).source;
      const isActive = branchEdges.some((edge) => edge.source === state.selectedGraphNodeId || edge.target === state.selectedGraphNodeId);

      const paths = branch.axis === "bottom"
        ? routeBottomGroupPaths(sourceAnchor, branch.branchY, targetAnchors)
        : routeVerticalGroupPaths(sourceAnchor, branch.branchX, targetAnchors);

      return paths.map((path) => `<path class="graph-edge${isActive ? " active" : ""}" d="${path}"></path>`);
    }),
  ].join("");

  applyGraphZoom();
  updateGraphContextBar(graph, normalizedEdges);
  updateGraphActionBar();
}

function selectedGraphNodeRecord() {
  return state.currentGraph?.nodes?.find((node) => node.id === state.selectedGraphNodeId) || null;
}

function selectedGraphBranchType() {
  const selectedId = state.selectedGraphNodeId;
  if (!selectedId || !state.currentGraph) return null;
  const edge = (state.currentGraph.edges || []).find((item) => item.source === selectedId || item.target === selectedId);
  if (!edge) return null;
  return edge.type === "SUPPLIES" ? "SUPPLIED_BY" : edge.type;
}

function updateGraphActionBar() {
  const branchType = selectedGraphBranchType();
  const selectedNode = selectedGraphNodeRecord();
  const collapse = document.getElementById("graph-collapse-branch");
  const expand = document.getElementById("graph-expand-branch");
  const pin = document.getElementById("graph-pin-node");
  const evidence = document.getElementById("graph-open-evidence");
  const compare = document.getElementById("graph-compare-node");
  if (collapse) collapse.disabled = !branchType || state.graphCollapsedTypes.includes(branchType);
  if (expand) expand.disabled = !branchType || !state.graphCollapsedTypes.includes(branchType);
  if (pin) pin.textContent = state.graphPinnedNodeIds.includes(state.selectedGraphNodeId) ? "Unpin node" : "Pin node";
  if (evidence) evidence.disabled = !selectedNode;
  if (compare) compare.disabled = !selectedNode || selectedNode.type !== "material";
}

async function sendEntityToReview(candidateType, reason, payload = {}) {
  if (!state.currentUser) {
    setStatus("review-status", "Sign in before sending an item to review.", "error");
    return;
  }
  await fetchJson("/review-candidates/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_type: candidateType, reason, payload }),
  });
  setPage("workbench");
  setStatus("review-status", "Moved the current context into the review queue.", "success");
  syncActiveCase({ review_state: "pending_human_review", status: "review", workflow_step: "Review" });
  await Promise.all([loadReviewQueue(), loadNotifications()]);
}

async function openMaterial(materialId, page = "overview") {
  if (!materialId) return;
  state.selectedMaterialId = materialId;
  state.latestSupplierId = null;
  const select = document.getElementById("material-select");
  if (select) select.value = materialId;
  setPage(page);
  await refreshMaterialContext();
  const material = state.materials.find((item) => item.material_id === materialId);
  if (material) {
    pushRecentEntity({ id: materialId, label: material.name, type: "material" });
  }
  syncActiveCase({
    focus_material_id: materialId,
    focus_supplier_id: null,
    focus_entity_type: "material",
    focus_entity_id: materialId,
    focus_entity_name: material?.name || "",
    status: page === "overview" ? "discover" : page === "workbench" ? "compare" : "validate",
    workflow_step: page === "overview" ? "Discover" : page === "workbench" ? "Compare" : "Validate",
  });
}

async function openSupplierProfile(supplierId) {
  state.latestSupplierId = supplierId;
  const supplier = await fetchJson(`/suppliers/${encodeURIComponent(supplierId)}`);
  renderSupplierDetail(supplier);
  setChatContext(buildSupplierChatContext(supplier));
  pushRecentEntity({ id: supplierId, label: supplier.name, type: "supplier" });
  setPage("intelligence");
  syncActiveCase({
    focus_supplier_id: supplierId,
    focus_entity_type: "supplier",
    focus_entity_id: supplierId,
    focus_entity_name: supplier.name,
    next_action_label: "Inspect supplier graph context",
    next_action_target: "intelligence",
    next_action_reason: "Review supplier-linked materials, risk trend, and nearby evidence before deciding.",
  });
  renderCrossPageContext();
}

async function openRegulationDetail(regulationId) {
  const regulation = await fetchJson(`/regulations/${encodeURIComponent(regulationId)}`);
  renderRegulationDetail(regulation);
  setChatContext(buildRegulationChatContext(regulation));
  pushRecentEntity({ id: regulationId, label: regulation.name, type: "regulation" });
  setPage("intelligence");
  syncActiveCase({
    focus_entity_type: "regulation",
    focus_entity_id: regulationId,
    focus_entity_name: regulation.name,
    next_action_label: "Validate exposed materials",
    next_action_target: "intelligence",
    next_action_reason: "Use regulation detail to review affected materials, evidence gaps, and likely actions.",
  });
  renderCrossPageContext();
}

function addMaterialToShortlist(materialId) {
  const compare = document.getElementById("compare-materials");
  if (!compare) return;
  const option = Array.from(compare.options).find((item) => item.value === materialId);
  if (!option) return;
  option.selected = true;
  renderCompareSelectionSummary();
  syncActiveCase({
    shortlist_material_ids: selectedMaterialsFromCompare(),
    status: "compare",
    workflow_step: "Compare",
  });
}

function bindInlineActions() {
  document.querySelectorAll("[data-select-material]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openMaterial(button.dataset.selectMaterial, "overview");
    });
  });
  document.querySelectorAll("[data-open-graph]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openMaterial(button.dataset.openGraph, "intelligence");
    });
  });
  document.querySelectorAll("[data-shortlist-material]").forEach((button) => {
    button.addEventListener("click", () => {
      addMaterialToShortlist(button.dataset.shortlistMaterial);
      setPage("workbench");
    });
  });
  document.querySelectorAll("[data-compare-material]").forEach((button) => {
    button.addEventListener("click", async () => {
      addMaterialToShortlist(button.dataset.compareMaterial);
      setPage("workbench");
      await runComparison();
    });
  });
  document.querySelectorAll("[data-run-scenario]").forEach((button) => {
    button.addEventListener("click", async () => {
      setPage("workbench");
      document.getElementById("scenario-type").value = button.dataset.runScenario;
      if (window.PackGraphWorkbenchPanels) {
        window.PackGraphWorkbenchPanels.applyScenarioVisibility(button.dataset.runScenario);
      }
      await runScenario();
    });
  });
  document.querySelectorAll("[data-open-supplier]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openSupplierProfile(button.dataset.openSupplier);
    });
  });
  document.querySelectorAll("[data-open-regulation]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openRegulationDetail(button.dataset.openRegulation);
    });
  });
  document.querySelectorAll("[data-ask-component]").forEach((button) => {
    button.addEventListener("click", () => {
      setChatContext(buildComponentChatContext(button.dataset.askComponent), {
        open: true,
        prompt: `What should I know about the component ${button.dataset.askComponent} for packaging decisions?`,
      });
    });
  });
  document.querySelectorAll("[data-export-material]").forEach((button) => {
    button.addEventListener("click", () => {
      const materialId = button.dataset.exportMaterial;
      window.open(`/exports/executive-summary.pdf?material_id=${encodeURIComponent(materialId)}`, "_blank", "noopener");
    });
  });
  document.querySelectorAll("[data-send-review]").forEach((button) => {
    button.addEventListener("click", async () => {
      await sendEntityToReview(
        button.dataset.reviewType || "material_decision",
        button.dataset.reviewReason || "Manual review requested from the UI.",
        {
          entity_id: button.dataset.sendReview,
          entity_type: button.dataset.reviewType || "material",
          display_name: button.dataset.reviewLabel || button.dataset.sendReview,
          provenance_snippets: [button.dataset.reviewContext || "Sent from PackGraph UI."],
        }
      );
    });
  });
  document.querySelectorAll("[data-open-evidence]").forEach((button) => {
    button.addEventListener("click", async () => {
      setPage("workbench");
      await loadDocumentPreview(button.dataset.openEvidence);
    });
  });
}

function selectedMaterialsFromCompare() {
  return Array.from(document.getElementById("compare-materials").selectedOptions).map((option) => option.value);
}

function selectedMaterialRecordsFromCompare() {
  const ids = selectedMaterialsFromCompare();
  return ids.map((id) => state.materials.find((item) => item.material_id === id)).filter(Boolean);
}

function renderShortlistSummaryRibbon() {
  const container = document.getElementById("shortlist-summary-ribbon");
  if (!container) return;
  const selected = selectedMaterialRecordsFromCompare();
  if (!selected.length) {
    container.innerHTML = `
      <div class="shortlist-summary-copy">
        <span class="section-label">Shortlist state</span>
        <strong>No active shortlist yet</strong>
        <p>Select candidates to keep comparison context visible while you review rankings and evidence.</p>
      </div>`;
    return;
  }
  const names = selected.map((item) => item.name).join(", ");
  container.innerHTML = `
    <div class="shortlist-summary-copy">
      <span class="section-label">Shortlist state</span>
      <strong>${selected.length} candidates active</strong>
      <p>${escapeHtml(names)}</p>
    </div>
    <div class="shortlist-summary-meta">
      <div><span>Primary task</span><strong>Compare and validate</strong></div>
      <div><span>Best next move</span><strong>Run ranking or inspect evidence</strong></div>
    </div>`;
}

function renderCompareSelectionSummary() {
  const container = document.getElementById("compare-selection-summary");
  if (!container) return;
  const selected = selectedMaterialRecordsFromCompare();
  container.innerHTML = selected.length
    ? selected.map((item) => `<span class="pill">${escapeHtml(item.name)}</span>`).join("")
    : `<span class="pill">No shortlist selected yet</span>`;
  renderShortlistSummaryRibbon();
}

function updatePageContextCard() {
  const pageCard = document.getElementById("page-context-card");
  if (!pageCard) return;
  if (state.currentSection !== "dashboard") {
    const shellDescriptions = {
      explore: "Browse-first research: materials, applications, suppliers, and source-driven updates.",
      contribute: "Role-based onboarding and contribution workflow for insights, evidence, and links.",
      community: "Topic channels, post feed, and discussion detail around materials intelligence.",
    };
    pageCard.innerHTML = `<span>Current page</span><strong>${titleCase(state.currentSection)}</strong><small>${shellDescriptions[state.currentSection]}</small>`;
    return;
  }
  const descriptions = {
    overview: "Discover and evaluate: search, structured answer, compliance, and candidate triage.",
    workbench: "Compare and validate: shortlist, evidence, scenarios, review, and case trail.",
    intelligence: "Context and monitoring: graph, analytics, alerts, and supporting detail.",
  };
  pageCard.innerHTML = `<span>Current page</span><strong>${titleCase(state.currentPage)}</strong><small>${descriptions[state.currentPage]}</small>`;
}

function renderCrossPageContext() {
  const container = document.getElementById("cross-page-context");
  if (!container) return;
  const material = state.materials.find((item) => item.material_id === state.selectedMaterialId);
  const shortlist = selectedMaterialRecordsFromCompare();
  const supplier = state.suppliers.find((item) => item.supplier_id === state.latestSupplierId);
  const activeCase = state.activeCase || defaultActiveCase();
  const chips = window.PackGraphWorkflow.contextChips(activeCase, {
    materialName: material?.name,
    supplierName: supplier?.name,
    latestQuestion: state.latestQuestion,
    latestGlobalSearch: state.latestGlobalSearch,
    shortlistNames: shortlist.map((item) => item.name),
  });
  container.innerHTML = chips.length
    ? chips.map((chip) => `<span class="pill">${escapeHtml(chip.label)}: ${escapeHtml(chip.value)}</span>`).join("")
    : `<span class="pill">No cross-page context captured yet</span>`;
}

function renderRecommendedNextAction(panel) {
  const container = document.getElementById("answer-next-action");
  if (!container) return;
  const actionPayload = panel?.recommended_action || {};
  const title = actionPayload.label || "Refine on Overview";
  const body = actionPayload.reason || "Use the current result to decide the best next workspace.";
  const target = actionPayload.target || "overview";

  container.innerHTML = `
    <span class="section-label">Recommended next action</span>
    <strong>${escapeHtml(title)}</strong>
    <p>${escapeHtml(body)}</p>
    <div class="row-actions">
      <button type="button" class="secondary overview-nav-button" data-jump-page="${target}">${escapeHtml(title)}</button>
    </div>`;
}

function populateMaterialControls(materials) {
  const select = document.getElementById("material-select");
  const compare = document.getElementById("compare-materials");
  select.innerHTML = materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("");
  compare.innerHTML = state.materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("");
  if (!materials.find((item) => item.material_id === state.selectedMaterialId)) {
    state.selectedMaterialId = materials[0]?.material_id || state.materials[0]?.material_id;
  }
  select.value = state.selectedMaterialId;
  const currentSelections = selectedMaterialsFromCompare();
  const fallbackSelections = currentSelections.length ? currentSelections : state.materials.slice(0, 3).map((item) => item.material_id);
  Array.from(compare.options).forEach((option) => {
    option.selected = fallbackSelections.includes(option.value);
  });
  renderCompareSelectionSummary();
}

function setPage(pageName) {
  state.currentSection = "dashboard";
  state.currentPage = pageName;
  document.body.setAttribute("data-page", pageName);
  document.querySelectorAll(".page-link").forEach((button) => button.classList.toggle("active", button.dataset.page === pageName));
  document.querySelectorAll(".page-section").forEach((section) => section.classList.toggle("active", section.dataset.page === pageName));
  document.querySelectorAll(".product-section").forEach((section) => section.classList.toggle("active", section.dataset.section === "dashboard"));
  document.querySelectorAll(".shell-link").forEach((button) => button.classList.toggle("active", button.dataset.section === "dashboard"));
  updatePageContextCard();
  const currentUrl = new URL(window.location.href);
  currentUrl.searchParams.set("section", "dashboard");
  currentUrl.searchParams.set("page", pageName);
  window.history.replaceState({}, "", currentUrl);
  syncActiveCase(window.PackGraphWorkflow.stateFromPage(pageName));
}

function setSection(sectionName) {
  state.currentSection = sectionName;
  document.querySelectorAll(".shell-link").forEach((button) => button.classList.toggle("active", button.dataset.section === sectionName));
  document.querySelectorAll(".product-section").forEach((section) => section.classList.toggle("active", section.dataset.section === sectionName));
  updatePageContextCard();
  const currentUrl = new URL(window.location.href);
  currentUrl.searchParams.set("section", sectionName);
  if (sectionName !== "dashboard") {
    currentUrl.searchParams.delete("page");
  }
  window.history.replaceState({}, "", currentUrl);
  const workflowState = window.PackGraphWorkflow.stateFromSection(sectionName);
  if (workflowState) {
    syncActiveCase(workflowState);
  }
}

async function loadSession() {
  try {
    state.currentUser = await fetchJson("/auth/session");
  } catch {
    state.currentUser = null;
  }
  if (!state.currentUser) {
    setSessionToken("");
  }
  if (window.PackGraphAuthShell) {
    window.PackGraphAuthShell.renderUser(state.currentUser);
  }
  renderRoleDashboard();
}

async function loadProjectMemory() {
  try {
    state.projectMemory = await fetchJson("/project-memory");
    const memory = state.projectMemory || {};
    const savedEntities = memory.saved_entities || [];
    const comparedEntities = memory.compared_entities || [];
  syncActiveCase({
      focus_material_id: state.activeCase?.focus_material_id || savedEntities[0] || null,
      shortlist_material_ids: state.activeCase?.shortlist_material_ids?.length ? state.activeCase.shortlist_material_ids : comparedEntities,
      latest_question: state.activeCase?.latest_question || (memory.prior_questions || []).slice(-1)[0] || "",
      note: state.activeCase?.note || (memory.investigation_notes || []).slice(-1)[0] || "",
      focus_entity_id: state.activeCase?.focus_entity_id || savedEntities[0] || null,
      focus_entity_name: state.activeCase?.focus_entity_name || "",
    });
  } catch {
    state.projectMemory = null;
  }
}

async function loadPrivateDataStatus() {
  try {
    state.privateDataStatus = await fetchJson("/private-data/status");
  } catch {
    state.privateDataStatus = { private_data_active: false, dataset_count: 0, record_count: 0 };
  }
  renderPromptDiary();
}

async function loadMaterials() {
  const payload = await fetch("/materials");
  const body = await payload.json();
  state.materials = body.data;
  state.products = await fetchJson("/products");
  state.suppliers = await fetchJson("/suppliers?page=1&limit=100");
  state.supplierRegionSummary = await fetchJson("/suppliers/regions/summary");
  state.applications = await fetchJson("/applications");
  state.regulations = await fetchJson("/regulations");
  state.filteredMaterials = [...state.materials];
  state.selectedMaterialId = state.activeCase?.focus_material_id || state.materials[0]?.material_id;
  state.selectedGraphNodeId = state.selectedMaterialId;
  populateMaterialControls(state.materials);
  populateFilterOptions();
  populateExploreOptions();
  populateContributionEntityOptions();
  populateCommunityMaterialOptions();
  document.getElementById("material-select").addEventListener("change", async (event) => {
    state.selectedMaterialId = event.target.value;
    await refreshMaterialContext();
  });
  await refreshMaterialContext();
  renderCaseWorkspace();
  renderWorkflowMap();
}

function populateFilterOptions() {
  const regions = [...new Set(state.materials.flatMap((item) => item.regions_available))].sort();
  const categories = [...new Set(state.materials.map((item) => item.category))].sort();
  const regulations = state.regulations || [];
  document.getElementById("filter-region").innerHTML = `<option value="">All regions</option>${regions.map((item) => `<option value="${item}">${item}</option>`).join("")}`;
  document.getElementById("filter-category").innerHTML = `<option value="">All categories</option>${categories.map((item) => `<option value="${item}">${titleCase(item)}</option>`).join("")}`;
  document.getElementById("filter-regulation").innerHTML = `<option value="">Any regulation</option>${regulations.map((item) => `<option value="${item.regulation_id}">${item.name}</option>`).join("")}`;
}

function populateExploreOptions() {
  const categories = [...new Set([
    ...state.materials.map((item) => item.category),
    ...state.products.map((item) => item.industry_name),
  ])].sort();
  const supplierRegions = [...new Set(state.suppliers.flatMap((item) => item.regions_served || []))].sort();
  document.getElementById("explore-region").innerHTML = `<option value="">All supplier regions</option>${supplierRegions.map((item) => `<option value="${item}">${item}</option>`).join("")}`;
  document.getElementById("explore-category").innerHTML = `<option value="">All categories</option>${categories.map((item) => `<option value="${item}">${titleCase(item)}</option>`).join("")}`;
  document.getElementById("explore-supplier").innerHTML = `<option value="">All suppliers</option>${state.suppliers.map((item) => `<option value="${item.supplier_id}">${item.name}</option>`).join("")}`;
  document.getElementById("explore-application").innerHTML = `<option value="">All applications</option>${state.applications.map((item) => `<option value="${item.application_id}">${item.name}</option>`).join("")}`;
  renderSupplierRegionSummary();
}

function populateContributionEntityOptions() {
  const select = document.getElementById("contribution-entity-id");
  if (!select) return;
  const entityType = document.getElementById("contribution-entity-type")?.value || "material";
  let options = [];
  if (entityType === "material") options = state.materials.map((item) => [item.material_id, item.name]);
  if (entityType === "application") options = state.applications.map((item) => [item.application_id, item.name]);
  if (entityType === "supplier") options = state.suppliers.map((item) => [item.supplier_id, item.name]);
  if (entityType === "news") options = [["NEWS-001", "News update"], ["NEWS-002", "News update"], ["NEWS-003", "News update"]];
  select.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
}

function populateCommunityMaterialOptions() {
  const select = document.getElementById("community-related-material");
  const filter = document.getElementById("community-related-filter");
  if (select) {
    select.innerHTML = `<option value="">No linked material</option>${state.materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("")}`;
  }
  if (filter) {
    filter.innerHTML = `<option value="">Any linked material</option>${state.materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("")}`;
  }
}

async function refreshMaterialContext() {
  await Promise.all([loadMaterialDetail(), loadProvenance(), loadGraph(), loadMaterialTimeline()]);
}

async function loadMaterialDetail() {
  document.getElementById("material-detail").innerHTML = skeletonBlock("material");
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  state.selectedMaterialDetail = material;
  setChatContext(buildMaterialChatContext(material));
  document.getElementById("context-material").textContent = material.name;
  document.getElementById("overview-selected-material").textContent = material.name;
  document.getElementById("overview-selected-material-note").textContent = `${titleCase(material.category)} material across ${material.regions_available.length} regions with ${material.supplier_ids.length} qualified suppliers in the demo graph.`;
  document.getElementById("material-title").textContent = `${material.name} (${material.category})`;
  const supplierNames = material.suppliers.map((item) => item.name);
  const substitutes = material.substitute_material_ids.map((id) => state.materials.find((entry) => entry.material_id === id)?.name || id);
  document.getElementById("material-detail").innerHTML = `
    <div class="detail-primary overview-detail-primary">
      <div class="detail-card">
        <h5>Profile</h5>
        <h4>Current candidate</h4>
        <p>${material.composition}</p>
        ${formatTags(material.regions_available)}
        <div class="key-facts">
          <div class="fact"><span>Descriptor</span><strong>${titleCase(material.descriptor)}</strong></div>
          <div class="fact"><span>Food contact</span><strong>${material.food_contact_safe ? "Approved profile" : "Review required"}</strong></div>
          <div class="fact"><span>Applications</span><strong>${material.target_applications.length} active targets</strong></div>
          <div class="fact"><span>Suppliers</span><strong>${material.supplier_ids.length} qualified sources</strong></div>
        </div>
      </div>
      <div class="detail-card overview-metric-card">
        <h5>Key indicators</h5>
        <h4>Decision snapshot</h4>
        <div class="overview-metric-grid">
          <div class="metric"><div class="value">${material.sustainability_score}</div><div>Sustainability</div></div>
          <div class="metric"><div class="value">${material.recyclability_score}</div><div>Recyclability</div></div>
          <div class="metric"><div class="value">${material.compostability_score}</div><div>Compostability</div></div>
          <div class="metric"><div class="value">${material.cost_range.low}-${material.cost_range.high}</div><div>${material.cost_range.currency} / kg</div></div>
        </div>
      </div>
    </div>
    <div class="detail-secondary overview-detail-secondary">
      <div class="detail-card">
        <h5>Compliance view</h5>
        <h4>State and substitutes</h4>
        <p>Current state: <strong>${titleCase(material.compliance_state)}</strong></p>
        ${formatTags((material.compliance_flags.length ? material.compliance_flags : ["compliant profile"]).map(titleCase))}
        <div class="subsection">
          <div class="subsection-heading">Substitute materials</div>
          ${formatTags(substitutes)}
        </div>
      </div>
      <div class="detail-card">
        <h5>Qualified supply</h5>
        <h4>Available suppliers</h4>
        ${supplierNames.map((name) => `<div class="score-row"><span>${name}</span><strong>Available</strong></div>`).join("")}
      </div>
    </div>`;
  updateExportLinks(material);
  populateScenarioControls(material);
  renderRoleDashboard();
  syncActiveCase({
    focus_material_id: material.material_id,
  });
}

async function loadProvenance(searchQuery = "") {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  const previewPanel = document.getElementById("document-preview-panel");
  if (previewPanel) {
    previewPanel.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("Choose a source document", "Preview extracted fields, confidence, citation spans, and missing evidence here.")
      : `<div class="row-card"><p>Select a document or report to preview extracted fields and source context.</p></div>`;
  }
  document.getElementById("provenance-panel").innerHTML = `
    <div class="detail-card">
      <h4>Documents</h4>
      ${material.documents.map((doc) => `<div class="row-card"><strong>${doc.title}</strong><p>${titleCase(doc.document_type)}</p><small>Provenance score ${doc.provenance_score} / issued ${doc.issued_on}</small>${doc.extraction_summary ? `<p>${escapeHtml(doc.extraction_summary)}</p>` : ""}<div class="action-row"><button type="button" class="mini-action" data-open-document="${escapeHtml(doc.document_id)}">Preview</button></div></div>`).join("")}
    </div>
    <div class="detail-card">
      <h4>Test reports</h4>
      ${material.test_reports.map((report) => `<div class="row-card"><strong>${report.title}</strong><p>${report.lab}</p><small>Migration ${report.migration_status} / test date ${report.test_date}</small>${report.extraction_summary ? `<p>${escapeHtml(report.extraction_summary)}</p>` : ""}<div class="action-row"><button type="button" class="mini-action" data-open-document="${escapeHtml(report.report_id)}">Preview</button></div></div>`).join("")}
    </div>`;
  if (searchQuery) {
    const results = await fetchJson(`/documents/search?query=${encodeURIComponent(searchQuery)}&material_id=${state.selectedMaterialId}`);
    renderTableCard(
      "document-search-results",
      [
        { label: "Evidence", render: (item) => `<strong>${escapeHtml(item.title || item.report_id || "Evidence")}</strong>` },
        { label: "Type", render: (item) => escapeHtml(titleCase(item.type)) },
        { label: "Detail", render: (item) => escapeHtml(item.document_type || item.lab || item.migration_status || "") },
        {
          label: "Actions",
          render: (item) => `
            <div class="action-row">
              <button type="button" class="mini-action" data-open-document="${escapeHtml(item.document_id || item.report_id || "")}">Preview</button>
              <button type="button" class="mini-action" data-open-graph="${escapeHtml(item.material_id || state.selectedMaterialId)}">Open in graph</button>
              <button type="button" class="mini-action" data-export-material="${escapeHtml(item.material_id || state.selectedMaterialId)}">Export</button>
            </div>`,
        },
      ],
      results,
      "Try another search phrase or review the reference evidence for the selected material."
    );
    bindInlineActions();
    if (window.PackGraphWorkbenchPanels) {
      window.PackGraphWorkbenchPanels.renderEvidenceExtraction(results);
    }
  } else {
    document.getElementById("document-search-results").innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("Search the proof set", "Search evidence to narrow declarations, reports, and certifications for the selected material.")
      : `<div class="table-empty">Search evidence to narrow the proof set for the selected material.</div>`;
    if (window.PackGraphWorkbenchPanels) {
      window.PackGraphWorkbenchPanels.renderEvidenceExtraction([...(material.documents || []), ...(material.test_reports || [])]);
    }
  }
  syncActiveCase({
    evidence_strength: material.documents?.length || material.test_reports?.length ? "moderate" : "weak",
    status: "validate",
    workflow_step: "Validate",
    next_action_label: "Inspect evidence detail",
    next_action_target: "workbench",
    next_action_reason: "Use Workbench to confirm extracted fields, confidence, and missing proof before approval.",
  });
  bindDocumentPreviewActions();
}

function bindDocumentPreviewActions() {
  document.querySelectorAll("[data-open-document]").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadDocumentPreview(button.dataset.openDocument);
    });
  });
}

async function loadDocumentPreview(documentId) {
  const container = document.getElementById("document-preview-panel");
  if (!container || !documentId) return;
  const detail = await fetchJson(`/documents/${encodeURIComponent(documentId)}`);
  setChatContext(buildUploadedRecordChatContext(detail));
  container.innerHTML = `
    <div class="detail-card">
      <h5>${escapeHtml(detail.document_type || detail.lab || "Evidence")}</h5>
      <h4>${escapeHtml(detail.title || documentId)}</h4>
      <p>${escapeHtml(detail.preview_text || "No preview text available.")}</p>
      <div class="tags">
        <span class="tag">Confidence ${escapeHtml(detail.confidence_summary || "n/a")}</span>
        ${(detail.missing_fields || []).map((field) => `<span class="tag">Missing ${escapeHtml(field)}</span>`).join("")}
        ${(detail.pii_flags || []).map((field) => `<span class="tag">PII ${escapeHtml(field)}</span>`).join("")}
      </div>
      <div class="key-facts">
        ${(detail.extracted_fields || []).map((field) => `<div class="fact"><span>${escapeHtml(field.label)}</span><strong>${escapeHtml(field.value)}</strong></div>`).join("")}
      </div>
      ${(detail.field_confidence || []).length ? `<div class="subsection"><div class="subsection-heading">Field confidence</div>${detail.field_confidence.map((field) => `<div class="score-row"><span>${escapeHtml(field.field_name)}</span><strong>${escapeHtml(Math.round((field.confidence || 0) * 100))}%</strong></div>`).join("")}</div>` : ""}
      ${(detail.citation_spans || []).length ? `<div class="subsection"><div class="subsection-heading">Citation spans</div>${detail.citation_spans.map((item) => `<div class="row-card"><p>${escapeHtml(item)}</p></div>`).join("")}</div>` : ""}
    </div>`;
  syncActiveCase({
    focus_entity_type: "document",
    focus_entity_id: documentId,
    focus_entity_name: detail.title || documentId,
    evidence_strength: "strong",
    status: "validate",
    workflow_step: "Validate",
    next_action_label: "Keep validating evidence",
    next_action_target: "workbench",
    next_action_reason: "Review missing fields, citation spans, and source confidence before approving the case.",
    missing_evidence_count: (detail.missing_fields || []).length,
  });
}

async function loadCompliance() {
  const dashboard = await fetchJson("/compliance/dashboard");
  document.getElementById("compliance-summary").innerHTML = `
    <div class="metric"><div class="value">${dashboard.watch_count}</div><div>materials under review</div></div>
    <div class="metric"><div class="value">${dashboard.non_compliant_count}</div><div>materials out of bounds</div></div>`;
  document.getElementById("regulation-list").innerHTML = dashboard.upcoming_regulations.map((item) => `<span class="pill">${item.name}</span>`).join("");
  renderTableCard(
    "compliance-risk-list",
    [
      { label: "Material", render: (item) => `<strong>${escapeHtml(item.name)}</strong>` },
      { label: "Supplier risk", render: (item) => escapeHtml(String(item.supplier_risk_score)) },
      {
        label: "Actions",
        render: (item) => `
          <div class="action-row">
            <button type="button" class="mini-action" data-select-material="${escapeHtml(item.material_id)}">Open</button>
            <button type="button" class="mini-action" data-run-scenario="supplier_outage">Run scenario</button>
          </div>`,
      },
    ],
    dashboard.at_risk_materials.slice(0, 5),
    "No supplier exposure hotspots right now."
  );
  bindInlineActions();
  document.getElementById("hero-risk-count").textContent = dashboard.at_risk_materials.length;
  document.getElementById("hero-regulations").textContent = dashboard.upcoming_regulations.length;
}

async function loadAlerts() {
  const alerts = await fetchJson("/alerts?page=1&limit=12");
  document.getElementById("context-alerts").textContent = alerts.length;
  renderTableCard(
    "alerts-list",
    [
      { label: "Alert", render: (item) => `<strong>${escapeHtml(item.title)}</strong><br /><small>${escapeHtml(item.detail)}</small>` },
      { label: "Severity", render: (item) => `<span class="${riskClass(item.severity === "high" ? 80 : item.severity === "medium" ? 58 : 32)}">${escapeHtml(titleCase(item.severity))}</span>` },
      { label: "Category", render: (item) => `<span class="table-badge">${escapeHtml(titleCase(item.category))}</span>` },
    ],
    alerts,
    "No active alerts."
  );
}

async function uploadDocumentEvidence() {
  const fileInput = document.getElementById("document-upload-file");
  const status = document.getElementById("document-upload-status");
  const file = fileInput.files[0];
  if (!file) {
    setStatus("document-upload-status", "Choose a file before uploading evidence.", "error");
    return;
  }
  setStatus("document-upload-status", "Uploading evidence and extracting fields...", "info");
  const formData = new FormData();
  formData.set("file", file);
  formData.set("document_type", document.getElementById("document-upload-type").value);
  formData.set("material_id", state.selectedMaterialId);
  const title = document.getElementById("document-upload-title").value.trim();
  if (title) formData.set("title", title);

  const response = await fetch("/documents/upload", {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok || payload.status !== "ok") {
    setStatus("document-upload-status", payload.detail || payload.error || "Upload failed.", "error");
    return;
  }
  setStatus("document-upload-status", `Uploaded ${payload.data.record.title}. Extraction linked to ${state.selectedMaterialId}.`, "success");
  document.getElementById("document-upload-title").value = "";
  fileInput.value = "";
  await Promise.all([loadProvenance(document.getElementById("document-search-input").value.trim()), loadAlerts(), loadGraph()]);
}

function renderSourceIntakeProfile(payload) {
  const container = document.getElementById("source-intake-profile");
  if (!container) return;
  if (!payload) {
    container.innerHTML = window.PackGraphUI
      ? window.PackGraphUI.emptyState("No source extracted yet", "Upload a JSON or PDF source to see schema fields and reusable records.")
      : "";
    return;
  }
  const profile = payload.schema_profile || {};
  const fields = profile.fields || [];
  const source = payload.source || {};
  container.innerHTML = `
    <div class="metric-card">
      <span>Source</span>
      <strong>${escapeHtml(source.title || "Uploaded source")}</strong>
      <small>${escapeHtml(titleCase(source.source_type || "source"))} | ${Number(source.file_size || 0).toLocaleString()} bytes</small>
    </div>
    <div class="metric-card">
      <span>Schema</span>
      <strong>${Number(profile.field_count || 0).toLocaleString()} fields</strong>
      <small>${Number(profile.record_count || payload.stored_record_count || 0).toLocaleString()} reusable records</small>
    </div>
    <div class="metric-card">
      <span>Quality</span>
      <strong>${payload.parse_errors?.length ? "Needs review" : "Parsed"}</strong>
      <small>${payload.parse_errors?.length || 0} parse issues detected</small>
    </div>
    <div class="table-card source-schema-table">
      ${fields.length
        ? `<table><thead><tr><th>Field</th><th>Type</th><th>Count</th></tr></thead><tbody>${fields.slice(0, 8).map((field) => `<tr><td>${escapeHtml(field.path)}</td><td>${escapeHtml((field.types || []).join(", "))}</td><td>${escapeHtml(field.count)}</td></tr>`).join("")}</tbody></table>`
        : window.PackGraphUI.emptyState("No structured fields", "The file was stored as searchable text for future prompts.")}
    </div>
  `;
}

function renderSourceIntakeSources() {
  renderTableCard(
    "source-intake-sources",
    [
      { label: "Source", render: (item) => `<strong>${escapeHtml(item.title)}</strong><br /><small>${escapeHtml(item.filename || "")}</small>` },
      { label: "Type", render: (item) => `<span class="table-badge">${escapeHtml(titleCase(item.source_type || "source"))}</span>` },
      { label: "Schema", render: (item) => `${Number(item.field_count || 0)} fields<br /><small>${Number(item.record_count || 0)} records</small>` },
      { label: "Action", render: (item) => `<button type="button" class="mini-action" data-source-chat="${escapeHtml(item.source_id)}">Use in graph chat</button>` },
    ],
    state.sourceIntakeSources || [],
    "No uploaded workspace sources yet."
  );
  document.querySelectorAll("[data-source-chat]").forEach((button) => {
    button.addEventListener("click", () => {
      const source = (state.sourceIntakeSources || []).find((item) => item.source_id === button.dataset.sourceChat);
      if (!source) return;
      setChatContext(
        {
          entity_type: "uploaded_record",
          entity_id: source.source_id,
          entity_name: source.title,
          metadata: {
            source_type: source.source_type,
            record_count: source.record_count,
            field_count: source.field_count,
          },
        },
        { open: true }
      );
      setStatus("source-intake-status", `${source.title} is now active in graph chat.`, "info");
    });
  });
}

async function loadSourceIntakeSources() {
  try {
    state.sourceIntakeSources = await fetchJson("/source-intake/sources?limit=20");
  } catch {
    state.sourceIntakeSources = [];
  }
  renderSourceIntakeSources();
  renderSourceIntakeProfile(state.latestSourceIntakeProfile);
}

async function uploadSourceIntake() {
  const fileInput = document.getElementById("source-intake-file");
  const file = fileInput?.files?.[0];
  if (!file) {
    setStatus("source-intake-status", "Choose a JSON or PDF source before extracting.", "error");
    return;
  }
  setStatus("source-intake-status", "Extracting schema and storing reusable records...", "info");
  const formData = new FormData();
  formData.set("file", file);
  const sourceType = document.getElementById("source-intake-type").value;
  const title = document.getElementById("source-intake-title").value.trim();
  if (sourceType) formData.set("source_type", sourceType);
  if (title) formData.set("title", title);
  try {
    const payload = await fetchJson("/source-intake/upload", {
      method: "POST",
      body: formData,
      retries: 0,
      timeoutMs: 30000,
    });
    state.latestSourceIntakeProfile = payload;
    const source = payload.source || {};
    renderSourceIntakeProfile(payload);
    await loadSourceIntakeSources();
    setChatContext(
      {
        entity_type: "uploaded_record",
        entity_id: source.source_id,
        entity_name: source.title,
        metadata: {
          source_type: source.source_type,
          record_count: source.record_count,
          field_count: source.field_count,
        },
      },
      { open: true }
    );
    await syncProjectMemory({ uploaded_file_references: [source.source_id], saved_entities: [source.source_id] });
    document.getElementById("source-intake-title").value = "";
    fileInput.value = "";
    setStatus("source-intake-status", `Stored ${source.title}. Future prompts can now use this source.`, "success");
  } catch (error) {
    setStatus("source-intake-status", error.message || "Source extraction failed.", "error");
  }
}

async function loadInvestigations() {
  const investigations = await fetchJson("/investigations");
  state.investigations = investigations;
  document.getElementById("context-investigations").textContent = investigations.length;
  document.getElementById("hero-investigations").textContent = investigations.length;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderInvestigations(investigations, resumeInvestigation);
  }
  renderActivityTimeline();
}

async function loadWorkspaces() {
  const workspaces = await fetchJson("/workspaces");
  state.workspaces = workspaces;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderWorkspaces(workspaces, resumeWorkspace);
  }
  renderSavedPresets();
}

async function loadNotifications() {
  try {
    state.notifications = await fetchJson("/notifications");
  } catch {
    state.notifications = [];
  }
  if (window.PackGraphAuthShell) {
    setNotificationFilter(state.notificationFilter);
  }
  renderActivityTimeline();
  renderRoleDashboard();
}

async function loadSavedSearches() {
  try {
    state.savedSearches = await fetchJson("/searches");
  } catch {
    state.savedSearches = [];
  }
  renderSavedSearches();
}

async function loadReviewQueue() {
  if (!state.currentUser) {
    state.reviewQueue = [];
    state.reviewSummary = { total: 0, pending: 0 };
    state.selectedReviewCandidateId = null;
    renderReviewQueue();
    return;
  }
  try {
    state.reviewQueue = await fetchJson("/review-candidates?page=1&limit=12");
    state.reviewSummary = await fetchJson("/review-candidates/summary");
    if (!state.selectedReviewCandidateId && state.reviewQueue.length) {
      state.selectedReviewCandidateId = state.reviewQueue[0].candidate_id;
    }
  } catch {
    state.reviewQueue = [];
    state.reviewSummary = { total: 0, pending: 0 };
    state.selectedReviewCandidateId = null;
  }
  renderReviewQueue();
  renderRoleDashboard();
}

function renderReviewQueue() {
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderReviewQueue(
      state.reviewSummary,
      state.reviewQueue,
      state.selectedReviewCandidateId,
      (candidateId) => {
        state.selectedReviewCandidateId = candidateId;
        renderReviewQueue();
      }
    );
  }
  const detailContainer = document.getElementById("review-detail-panel");
  if (!detailContainer) return;
  const selected = state.reviewQueue.find((item) => item.candidate_id === state.selectedReviewCandidateId);
  if (!selected) {
    detailContainer.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No review item selected", "Approval detail will appear here once a review candidate is available.")
      : `<div class="row-card"><p>No review item selected.</p></div>`;
    return;
  }
  const payload = selected.payload || {};
  detailContainer.innerHTML = `
    <div class="detail-card">
      <h5>${escapeHtml(selected.candidate_type.replaceAll("_", " "))}</h5>
      <h4>${escapeHtml(selected.reason)}</h4>
      <p>${escapeHtml(selected.status.replaceAll("_", " "))} | reviewer ${escapeHtml(selected.assigned_reviewer_id || "unassigned")}</p>
      <div class="tags">
        <span class="tag">Decision ${escapeHtml(selected.decision_state || "new")}</span>
        <span class="tag">Review before writeback ${selected.review_before_writeback ? "yes" : "no"}</span>
      </div>
      <div class="structured-next-action review-guidance-card">
        <span class="section-label">Review guidance</span>
        <strong>${escapeHtml(selected.assigned_reviewer_id ? "Decision can be taken now." : "Assign this item before deciding.")}</strong>
        <p>${escapeHtml((payload.missing_evidence || []).length ? "Missing proof is present, so keep the decision grounded in evidence before approving." : "Use the candidate summary and top rows to decide whether the item can move forward.")}</p>
      </div>
      ${(payload.missing_evidence || []).length ? `<div class="subsection"><div class="subsection-heading">Missing evidence</div>${payload.missing_evidence.map((item) => `<div class="row-card"><p>${escapeHtml(item)}</p></div>`).join("")}</div>` : ""}
      ${(payload.top_rows || []).length ? `<div class="subsection"><div class="subsection-heading">Top rows</div>${payload.top_rows.map((row) => `<div class="row-card"><strong>${escapeHtml(row.label || row.material_id || row.entity_id || "Candidate")}</strong><p>Score ${escapeHtml(String(row.score ?? ""))}</p></div>`).join("")}</div>` : ""}
    </div>`;
}

async function assignSelectedReviewToCurrentUser() {
  const selected = state.reviewQueue.find((item) => item.candidate_id === state.selectedReviewCandidateId);
  if (!selected || !state.currentUser) {
    setStatus("review-status", "Sign in and choose a review item first.", "error");
    return;
  }
  try {
    await fetchJson(`/review-candidates/${encodeURIComponent(selected.candidate_id)}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer_id: state.currentUser.user_id }),
    });
    setStatus("review-status", "Assigned the review item to your account.", "success");
    await Promise.all([loadReviewQueue(), loadNotifications()]);
  } catch (error) {
    setStatus("review-status", error.message, "error");
  }
}

async function applyReviewDecision(status) {
  const selected = state.reviewQueue.find((item) => item.candidate_id === state.selectedReviewCandidateId);
  if (!selected) {
    setStatus("review-status", "Choose a review item first.", "error");
    return;
  }
  const comment = document.getElementById("review-comment").value.trim();
  try {
    await fetchJson(`/review-candidates/${encodeURIComponent(selected.candidate_id)}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, comment, metadata: selected.payload || {} }),
    });
    document.getElementById("review-comment").value = "";
    setStatus("review-status", `Review item moved to ${status.replaceAll("_", " ")}.`, "success");
    syncActiveCase({
      review_state: status,
      status: "review",
      workflow_step: "Review",
      next_action_label: status === "approved" ? "Export the case" : "Continue validation",
      next_action_target: "workbench",
      next_action_reason: status === "approved"
        ? "The review cleared. Package the decision for stakeholders or export the case snapshot."
        : "Keep validating evidence and rationale before moving the case forward.",
    });
    await Promise.all([loadReviewQueue(), loadNotifications(), loadOperationsDashboard()]);
  } catch (error) {
    setStatus("review-status", error.message, "error");
  }
}

function renderSavedSearches() {
  const container = document.getElementById("explore-saved-searches");
  if (!container) return;
  if (!state.savedSearches.length) {
    container.innerHTML = `<div class="row-card"><p>No saved searches yet.</p></div>`;
    return;
  }
  container.innerHTML = state.savedSearches.slice(0, 6).map((item) => `
    <button type="button" class="row-card saved-search-card" data-saved-search="${escapeHtml(item.saved_search_id)}">
      <strong>${escapeHtml(item.name || item.tab || "Saved search")}</strong>
      <small>${escapeHtml(titleCase(item.tab || "materials"))} | ${escapeHtml(item.saved_at || "")}</small>
    </button>`).join("");
  container.querySelectorAll("[data-saved-search]").forEach((button) => {
    button.addEventListener("click", async () => {
      const search = state.savedSearches.find((item) => item.saved_search_id === button.dataset.savedSearch);
      if (!search) return;
      state.exploreTab = search.tab || "materials";
      state.exploreView = search.view || "cards";
      document.getElementById("explore-search").value = search.filters?.search || "";
      document.getElementById("explore-hero-input").value = search.filters?.search || "";
      document.getElementById("explore-taxonomy").value = search.filters?.taxonomy || "";
      document.getElementById("explore-region").value = search.filters?.region || "";
      document.getElementById("explore-category").value = search.filters?.category || "";
      document.getElementById("explore-supplier").value = search.filters?.supplier_id || "";
      document.getElementById("explore-application").value = search.filters?.application_id || "";
      document.getElementById("explore-compliance").value = search.filters?.compliance_state || "";
      document.getElementById("explore-sustainability").value = search.filters?.min_sustainability || "";
      await loadExploreEntities();
    });
  });
}

function renderSavedPresets() {
  const container = document.getElementById("saved-preset-list");
  if (!container) return;
  const presets = (state.workspaces || []).slice(0, 5);
  if (!presets.length) {
    container.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No saved presets", "Save a graph, filter, supplier, or investigation setup to restore it later.")
      : `<div class="row-card"><p>No saved presets yet.</p></div>`;
    return;
  }
  container.innerHTML = presets.map((item) => {
    const presetType = item.filters?.preset_type || "case";
    const graphSummary = item.filters?.graph_preset ? ` | ${item.filters.graph_preset} graph` : "";
    return `
      <button type="button" class="row-card saved-search-card saved-preset-card" data-resume-preset="${escapeHtml(item.workspace_id)}">
        <strong>${escapeHtml(item.name)}</strong>
        <small>${escapeHtml(titleCase(presetType))} | ${escapeHtml(titleCase(item.active_tab || "overview"))}${escapeHtml(graphSummary)}</small>
      </button>`;
  }).join("");
  container.querySelectorAll("[data-resume-preset]").forEach((button) => {
    button.addEventListener("click", async () => {
      await resumeWorkspace(button.dataset.resumePreset);
      setStatus("workspace-status", "Restored the saved preset.", "success");
    });
  });
}

async function saveCurrentExploreSearch() {
  const payload = {
    name: `${titleCase(state.exploreTab)} search`,
    tab: state.exploreTab,
    view: state.exploreView,
    filters: {
      search: document.getElementById("explore-search")?.value.trim() || "",
      taxonomy: document.getElementById("explore-taxonomy")?.value || "",
      region: document.getElementById("explore-region")?.value || "",
      category: document.getElementById("explore-category")?.value || "",
      supplier_id: document.getElementById("explore-supplier")?.value || "",
      application_id: document.getElementById("explore-application")?.value || "",
      compliance_state: document.getElementById("explore-compliance")?.value || "",
      min_sustainability: document.getElementById("explore-sustainability")?.value || "",
    },
  };
  const optimistic = {
    saved_search_id: `local-search-${Date.now()}`,
    name: payload.name,
    filters: payload.filters,
    tab: payload.tab,
    view: payload.view,
    pending: true,
  };
  state.savedSearches = [optimistic, ...(state.savedSearches || [])].slice(0, 12);
  renderSavedSearches();
  try {
    await fetchJson("/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus("explore-status", "Saved the current Explore search.", "success");
    await loadSavedSearches();
  } catch (error) {
    state.savedSearches = (state.savedSearches || []).filter((item) => item.saved_search_id !== optimistic.saved_search_id);
    renderSavedSearches();
    throw error;
  }
}

function renderSupplierRegionSummary() {
  const container = document.getElementById("supplier-region-summary");
  if (!container) return;
  if (!state.supplierRegionSummary.length) {
    container.innerHTML = `<div class="row-card"><p>No supplier geography data yet.</p></div>`;
    return;
  }
  const activeRegion = document.getElementById("explore-region")?.value || "";
  container.innerHTML = state.supplierRegionSummary.map((item) => `
    <button
      type="button"
      class="row-card saved-search-card ${activeRegion === item.region ? "is-active" : ""}"
      data-supplier-region="${escapeHtml(item.region)}"
    >
      <strong>${escapeHtml(item.region)}</strong>
      <small>${escapeHtml(String(item.supplier_count))} suppliers serve this region</small>
    </button>
  `).join("");
  container.querySelectorAll("[data-supplier-region]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.exploreTab = state.exploreTab === "news" ? "materials" : state.exploreTab;
      const selected = button.dataset.supplierRegion;
      const regionSelect = document.getElementById("explore-region");
      if (regionSelect) {
        regionSelect.value = regionSelect.value === selected ? "" : selected;
      }
      await loadExploreEntities();
    });
  });
}

async function loadExploreEntities() {
  const params = new URLSearchParams({ tab: state.exploreTab });
  const search = document.getElementById("explore-search")?.value.trim() || document.getElementById("explore-hero-input")?.value.trim();
  const taxonomy = document.getElementById("explore-taxonomy")?.value;
  const region = document.getElementById("explore-region")?.value;
  const category = document.getElementById("explore-category")?.value;
  const supplierId = document.getElementById("explore-supplier")?.value;
  const applicationId = document.getElementById("explore-application")?.value;
  const complianceState = document.getElementById("explore-compliance")?.value;
  const minSustainability = document.getElementById("explore-sustainability")?.value;
  if (search) params.set("search", search);
  if (taxonomy) params.set("taxonomy", taxonomy);
  if (region) params.set("region", region);
  if (category) params.set("category", category);
  if (supplierId) params.set("supplier_id", supplierId);
  if (applicationId) params.set("application_id", applicationId);
  if (complianceState) params.set("compliance_state", complianceState);
  if (minSustainability) params.set("min_sustainability", minSustainability);
  params.set("page", "1");
  params.set("limit", state.exploreView === "graph" ? "18" : "24");
  renderSurfaceState("explore-results", "loading", "Loading browse results", "PackGraph is assembling materials, products, or updates for the current filter set.");
  setStatus("explore-status", "Loading browse results...", "info");
  try {
    state.exploreResults = await fetchJson(`/explore/entities?${params.toString()}`);
  } catch (error) {
    renderSurfaceState("explore-results", "error", "Explore could not load", error.message);
    setStatus("explore-status", error.message, "error");
    return;
  }
  const searchReason = search ? `Matched "${search}" in the current ${state.exploreTab} browse set.` : "Matched the current filter set.";
  state.exploreResults = state.exploreResults.map((item) => ({ ...item, match_reason: item.match_reason || searchReason }));
  const sortValue = document.getElementById("explore-sort")?.value || "relevance";
  if (sortValue === "title") {
    state.exploreResults.sort((a, b) => a.title.localeCompare(b.title));
  }
  if (sortValue === "sustainability") {
    state.exploreResults.sort((a, b) => {
      const aValue = Number((a.meta || "").match(/Sustainability (\d+)/)?.[1] || 0);
      const bValue = Number((b.meta || "").match(/Sustainability (\d+)/)?.[1] || 0);
      return bValue - aValue;
    });
  }
  document.getElementById("explore-results-title").textContent = `${titleCase(state.exploreTab)} browse results`;
  document.getElementById("explore-results-summary").textContent = `${state.exploreResults.length} records in ${titleCase(state.exploreTab)}`;
  document.getElementById("explore-active-view-label").textContent = `${titleCase(state.exploreView)} view`;
  if (window.PackGraphExplorePage) {
    window.PackGraphExplorePage.renderTabs(state.exploreTab, async (tab) => {
      state.exploreTab = tab;
      state.selectedExploreDetail = null;
      await loadExploreEntities();
      window.PackGraphExplorePage.renderDetail(null, jumpExploreToDashboard);
    });
    window.PackGraphExplorePage.renderViewSwitcher(state.exploreView, async (view) => {
      state.exploreView = view;
      await loadExploreEntities();
    });
    window.PackGraphExplorePage.renderResults(state.exploreResults, openExploreDetail, state.selectedExploreDetail?.entity_id, (materialId) => {
      addMaterialToShortlist(materialId);
      renderExploreCompareSummary();
    }, state.exploreView);
  }
  renderSupplierRegionSummary();
  renderExploreCompareSummary();
  clearStatus("explore-status");
}

async function openExploreDetail(entityType, entityId) {
  state.selectedExploreDetail = await fetchJson(`/explore/detail?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`);
  setChatContext(buildExploreDetailChatContext(state.selectedExploreDetail));
  if (window.PackGraphExplorePage) {
    window.PackGraphExplorePage.renderResults(state.exploreResults, openExploreDetail, entityId, (materialId) => {
      addMaterialToShortlist(materialId);
      renderExploreCompareSummary();
    }, state.exploreView);
    window.PackGraphExplorePage.renderDetail(state.selectedExploreDetail, jumpExploreToDashboard);
  }
}

async function jumpExploreToDashboard(detail) {
  setChatContext(buildExploreDetailChatContext(detail), {
    open: true,
    prompt: detail?.dashboard_prompt || "What should I inspect next in the graph?",
  });
  state.latestQuestion = detail?.dashboard_prompt || "";
  renderCrossPageContext();
}

function renderExploreCompareSummary() {
  const container = document.getElementById("explore-compare-summary");
  if (!container) return;
  const selected = selectedMaterialRecordsFromCompare();
  container.innerHTML = selected.length
    ? `
      <div class="shortlist-summary-copy">
        <span class="section-label">Compare from Explore</span>
        <strong>${selected.length} shortlisted candidates</strong>
        <p>${escapeHtml(selected.map((item) => item.name).join(", "))}</p>
      </div>`
    : `
      <div class="shortlist-summary-copy">
        <span class="section-label">Compare from Explore</span>
        <strong>No comparison set yet</strong>
        <p>Add a material from Explore to carry it straight into Workbench.</p>
      </div>`;
}

async function updateExploreAutocomplete(query) {
  const container = document.getElementById("explore-autocomplete");
  if (!container) return;
  if (!query || query.trim().length < 2) {
    container.innerHTML = "";
    return;
  }
  const suggestions = await fetchJson(`/explore/autocomplete?query=${encodeURIComponent(query.trim())}`);
  if (!suggestions.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = suggestions.map((item) => `
    <button type="button" class="explore-autocomplete-item" data-explore-suggestion="${escapeHtml(item.entity_type)}::${escapeHtml(item.entity_id)}::${escapeHtml(item.label)}">
      <strong>${escapeHtml(item.label)}</strong>
      <small>${escapeHtml(titleCase(item.entity_type))}</small>
    </button>
  `).join("");
  container.querySelectorAll("[data-explore-suggestion]").forEach((button) => {
    button.addEventListener("click", async () => {
      const [entityType, entityId, label] = button.dataset.exploreSuggestion.split("::");
      document.getElementById("explore-hero-input").value = label;
      document.getElementById("explore-search").value = label;
      container.innerHTML = "";
      await openExploreDetail(entityType, entityId);
    });
  });
}

async function loadContributionData() {
  renderSurfaceState("contribution-recent-list", "loading", "Loading contribution activity", "Recent submissions, review queue, and role guidance are loading.");
  renderSurfaceState("contribution-review-queue", "loading", "Loading review queue", "PackGraph is gathering contribution items for this org.");
  try {
    state.contributionRoles = await fetchJson("/contributions/roles");
    state.contributionData = await fetchJson("/contributions");
  } catch (error) {
    renderSurfaceState("contribution-recent-list", "error", "Contribute is unavailable", error.message);
    renderSurfaceState("contribution-review-queue", "error", "Review queue unavailable", error.message);
    setStatus("contribution-status", error.message, "error");
    return;
  }
  const roleSelect = document.getElementById("contribution-role");
  if (roleSelect) {
    roleSelect.innerHTML = state.contributionRoles.map((role) => `<option value="${role.role_id}">${role.title}</option>`).join("");
    roleSelect.value = state.selectedContributionRoleId;
  }
  if (window.PackGraphContributePage) {
    window.PackGraphContributePage.renderRoles(state.contributionRoles, state.selectedContributionRoleId, (roleId) => {
      state.selectedContributionRoleId = roleId;
      const select = document.getElementById("contribution-role");
      if (select) select.value = roleId;
      renderContributionRoleDetail();
      window.PackGraphContributePage.renderRoles(state.contributionRoles, state.selectedContributionRoleId, (nextRoleId) => {
        state.selectedContributionRoleId = nextRoleId;
        const nextSelect = document.getElementById("contribution-role");
        if (nextSelect) nextSelect.value = nextRoleId;
        renderContributionRoleDetail();
      });
    });
    renderContributionRoleDetail();
    window.PackGraphContributePage.renderSubmissions(state.contributionData);
  }
  bindContributionReviewActions();
}

function bindContributionReviewActions() {
  document.querySelectorAll("[data-review-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const reviewerNote = `Updated by ${state.currentUser?.name || "reviewer"} on ${new Date().toISOString().slice(0, 10)}.`;
      try {
        await fetchJson(`/contributions/${encodeURIComponent(button.dataset.reviewId)}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: button.dataset.reviewStatus, reviewer_note: reviewerNote }),
        });
        setStatus("contribution-status", `Contribution moved to ${button.dataset.reviewStatus.replace("_", " ")}.`, "success");
        await Promise.all([loadContributionData(), loadNotifications()]);
      } catch (error) {
        setStatus("contribution-status", error.message, "error");
      }
    });
  });
}

function renderContributionRoleDetail() {
  if (!window.PackGraphContributePage) return;
  const role = state.contributionRoles.find((item) => item.role_id === state.selectedContributionRoleId);
  window.PackGraphContributePage.renderRoleDetail(role);
}

async function submitContribution() {
  const payload = {
    role_id: document.getElementById("contribution-role").value,
    submission_type: document.getElementById("contribution-type").value,
    title: document.getElementById("contribution-title").value.trim(),
    summary: document.getElementById("contribution-summary").value.trim(),
    related_entity_type: document.getElementById("contribution-entity-type").value,
    related_entity_id: document.getElementById("contribution-entity-id").value,
    evidence_note: document.getElementById("contribution-evidence-note").value.trim(),
    edit_request: document.getElementById("contribution-edit-request").value.trim(),
    proposed_links: document.getElementById("contribution-proposed-links").value.trim(),
  };
  if (!payload.title) {
    setStatus("contribution-status", "Add a contribution title before submitting.", "error");
    return;
  }
  setStatus("contribution-status", "Submitting contribution for review...", "info");
  try {
    await fetchJson("/contributions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    document.getElementById("contribution-form").reset();
    clearDraft(DRAFT_STORAGE_KEYS.contribution);
    populateContributionEntityOptions();
    await Promise.all([loadContributionData(), loadNotifications()]);
    setStatus("contribution-status", `Submitted ${payload.title}.`, "success");
  } catch (error) {
    setStatus("contribution-status", error.message, "error");
  }
}

async function loadCommunityData() {
  renderSurfaceState("community-feed", "loading", "Loading community", "Threads, channels, and discussion context are loading.");
  renderSurfaceState("community-detail", "loading", "Loading thread detail", "Choose a discussion once the feed arrives.");
  try {
    state.communityChannels = await fetchJson("/community/channels");
  } catch (error) {
    renderSurfaceState("community-feed", "error", "Community is unavailable", error.message);
    renderSurfaceState("community-detail", "error", "Thread detail unavailable", error.message);
    setStatus("community-status", error.message, "error");
    return;
  }
  document.getElementById("community-channel-select").innerHTML = state.communityChannels.map((channel) => `<option value="${channel.channel_id}">${channel.name}</option>`).join("");
  document.getElementById("community-channel-select").value = state.selectedCommunityChannelId;
  if (window.PackGraphCommunityPage) {
    window.PackGraphCommunityPage.renderChannels(state.communityChannels, state.selectedCommunityChannelId, async (channelId) => {
      state.selectedCommunityChannelId = channelId;
      document.getElementById("community-channel-select").value = channelId;
      await loadCommunityPosts();
    });
  }
  await loadCommunityPosts();
}

async function loadCommunityPosts() {
  const moderation = document.getElementById("community-moderation-filter")?.value || "";
  const relatedEntityId = document.getElementById("community-related-filter")?.value || "";
  const params = new URLSearchParams({ channel_id: state.selectedCommunityChannelId });
  if (moderation) params.set("moderation_state", moderation);
  if (relatedEntityId) params.set("related_entity_id", relatedEntityId);
  params.set("page", "1");
  params.set("limit", "12");
  renderSurfaceState("community-feed", "loading", "Loading discussions", "PackGraph is gathering posts for the selected channel.");
  try {
    state.communityPosts = await fetchJson(`/community/posts?${params.toString()}`);
  } catch (error) {
    renderSurfaceState("community-feed", "error", "Discussions could not load", error.message);
    setStatus("community-status", error.message, "error");
    return;
  }
  if (!state.selectedCommunityPostId && state.communityPosts.length) {
    state.selectedCommunityPostId = state.communityPosts[0].post_id;
  }
    if (window.PackGraphCommunityPage) {
      window.PackGraphCommunityPage.renderPosts(state.communityPosts, state.selectedCommunityPostId, openCommunityPost, upvoteCommunityPost, saveCommunityPost, pinCommunityPost, sendCommunityPostToReview, useCommunityPostInCase);
    }
  if (state.selectedCommunityPostId) {
    await openCommunityPost(state.selectedCommunityPostId);
  } else if (window.PackGraphCommunityPage) {
    window.PackGraphCommunityPage.renderDetail(null);
  }
}

async function openCommunityPost(postId) {
  state.selectedCommunityPostId = postId;
  const post = await fetchJson(`/community/posts/${encodeURIComponent(postId)}`);
  if (window.PackGraphCommunityPage) {
    window.PackGraphCommunityPage.renderPosts(state.communityPosts, state.selectedCommunityPostId, openCommunityPost, upvoteCommunityPost, saveCommunityPost, pinCommunityPost, sendCommunityPostToReview, useCommunityPostInCase);
    window.PackGraphCommunityPage.renderDetail(post);
  }
  pushRecentEntity({ id: postId, label: post.title, type: "community_post" });
}

async function sendCommunityPostToReview(postId) {
  const post = state.communityPosts.find((item) => item.post_id === postId);
  if (!post) return;
  await sendEntityToReview("community_finding", `Community finding requires review: ${post.title}`, {
    entity_id: post.post_id,
    display_name: post.title,
    provenance_snippets: [post.body, ...(post.source_refs || []).slice(0, 2)],
  });
}

async function useCommunityPostInCase(postId) {
  const post = state.communityPosts.find((item) => item.post_id === postId);
  if (!post) return;
  const linkedMaterial = post.related_material_id || state.selectedMaterialId;
  if (linkedMaterial) {
    await openMaterial(linkedMaterial, "workbench");
  } else {
    setPage("workbench");
  }
  const notes = document.getElementById("investigation-notes");
  if (notes) {
    notes.value = `${notes.value ? `${notes.value}\n\n` : ""}Community finding: ${post.title}\n${post.body}`;
  }
  syncActiveCase({
    note: `Community finding added: ${post.title}`,
    workflow_step: "Compare",
    status: "compare",
  }, { syncMemory: true });
  addBookmark({ id: post.post_id, label: post.title, type: "community_post" });
  addActivityEvent("Community finding added", post.title, "community");
  setStatus("investigation-status", `Added ${post.title} into the current case draft.`, "success");
}

async function upvoteCommunityPost(postId) {
  await fetchJson(`/community/posts/${encodeURIComponent(postId)}/upvote`, { method: "POST" });
  await loadCommunityPosts();
}

async function saveCommunityPost(postId) {
  await fetchJson(`/community/posts/${encodeURIComponent(postId)}/save`, { method: "POST" });
  await loadCommunityPosts();
}

async function pinCommunityPost(postId) {
  try {
    await fetchJson(`/community/posts/${encodeURIComponent(postId)}/pin`, { method: "POST" });
    await Promise.all([loadCommunityPosts(), loadNotifications()]);
  } catch (error) {
    setStatus("community-status", error.message, "error");
  }
}

async function submitCommunityPost() {
  const payload = {
    channel_id: document.getElementById("community-channel-select").value,
    title: document.getElementById("community-post-title").value.trim(),
    body: document.getElementById("community-post-body").value.trim(),
    related_material_id: document.getElementById("community-related-material").value || null,
    source_reference: document.getElementById("community-source-reference").value.trim(),
  };
  if (!payload.title || !payload.body) {
    setStatus("community-status", "Add a title and discussion body before posting.", "error");
    return;
  }
  setStatus("community-status", "Publishing demo post...", "info");
  try {
    await fetchJson("/community/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    document.getElementById("community-post-form").reset();
    clearDraft(DRAFT_STORAGE_KEYS.communityPost);
    state.selectedCommunityChannelId = payload.channel_id;
    state.selectedCommunityPostId = null;
    await loadCommunityData();
    setStatus("community-status", `Created post ${payload.title}.`, "success");
    await loadNotifications();
  } catch (error) {
    setStatus("community-status", error.message, "error");
  }
}

async function loadScenarioHistory() {
  const history = await fetchJson("/scenarios/history");
  state.scenarioHistory = history;
  renderTableCard(
    "scenario-history",
    [
      { label: "Scenario", render: (item) => `<strong>${escapeHtml(titleCase(item.scenario_type))}</strong>` },
      {
        label: "Before",
        render: (item) => escapeHtml(
          `${item.before.material_id || "portfolio"} | ${item.before.supplier_id || item.before.options?.regulation_id || "auto"}`
        ),
      },
      {
        label: "After",
        render: (item) => `<div><strong>${escapeHtml(item.after.summary || "Completed")}</strong><br /><small>${escapeHtml(JSON.stringify(item.after.metrics || {}))}</small></div>`,
      },
    ],
    history.slice(0, 8),
    "Run a scenario to build a history of before/after outcomes."
  );
  renderScenarioComparison();
  renderActivityTimeline();
}

function renderScenarioComparison() {
  const container = document.getElementById("scenario-comparison");
  if (!container) return;
  if (!state.scenarioComparisons.length) {
    container.innerHTML = window.PackGraphUI?.emptyState
      ? window.PackGraphUI.emptyState("No scenario comparison yet", "Run two scenarios to compare before and after impact summaries side by side.")
      : `<div class="row-card"><p>Run two scenarios to compare their impacts side by side.</p></div>`;
    return;
  }
  container.innerHTML = state.scenarioComparisons.map((item, index) => `
    <div class="row-card scenario-compare-card">
      <div>
        <strong>${escapeHtml(titleCase(item.scenario))}</strong>
        <small>${escapeHtml(index === 0 ? "Earlier comparison slot" : "Latest comparison slot")}</small>
      </div>
      <div class="scenario-before-after">
        <div>
          <span class="section-label">Before</span>
          <p>${escapeHtml(item.before?.material_id || "portfolio")} | ${escapeHtml(item.before?.supplier_id || item.before?.options?.regulation_id || "auto scope")}</p>
        </div>
        <div>
          <span class="section-label">After</span>
          <p>${escapeHtml(item.summary || "Scenario completed")}</p>
        </div>
      </div>
      <div class="tags">${Object.entries(item.metrics || {}).slice(0, 4).map(([key, value]) => `<span class="tag">${escapeHtml(titleCase(key))}: ${escapeHtml(String(value))}</span>`).join("")}</div>
    </div>
  `).join("");
}

async function loadGraph() {
  document.getElementById("graph-nodes-layer").innerHTML = skeletonBlock("graph");
  const graph = await fetchJson(`/graph/subgraph?material_id=${state.selectedMaterialId}`);
  const nextSignature = JSON.stringify({
    material_id: state.selectedMaterialId,
    filter: state.graphFilter,
    preset: state.graphPreset,
    isolate: state.graphIsolateSelection,
    collapsed: state.graphCollapsedTypes,
    pinned: state.graphPinnedNodeIds,
    nodes: graph.nodes?.map((node) => node.id),
    edges: graph.edges?.map((edge) => `${edge.source}:${edge.type}:${edge.target}`),
  });
  state.currentGraph = graph;
  const graphNodeIds = new Set(graph.nodes.map((node) => node.id));
  if (!graphNodeIds.has(state.selectedGraphNodeId)) {
    state.selectedGraphNodeId = state.selectedMaterialId;
  }
  if (state.graphRenderSignature !== nextSignature) {
    renderGraphCanvas(graph);
    state.graphRenderSignature = nextSignature;
  } else {
    applyGraphZoom();
    updateGraphContextBar(graph, normalizeGraphEdges(graph, state.graphIsolateSelection ? state.selectedGraphNodeId : state.selectedMaterialId));
    updateGraphActionBar();
  }
  const selectors = [document.getElementById("graph-source"), document.getElementById("graph-target")];
  selectors.forEach((select) => {
    select.innerHTML = graph.nodes.map((node) => `<option value="${node.id}">${node.label}</option>`).join("");
  });
  document.getElementById("graph-source").value = state.selectedGraphNodeId;
  document.getElementById("graph-target").value = graph.nodes.find((node) => node.id !== state.selectedGraphNodeId)?.id || state.selectedGraphNodeId;
  document.querySelectorAll(".graph-node").forEach((button) => {
    button.classList.toggle("active", button.dataset.nodeId === state.selectedGraphNodeId);
    button.addEventListener("click", async () => {
      await selectGraphNode(button.dataset.nodeId);
    });
  });
  const links = await fetchJson(`/graph/relationships?material_id=${state.selectedMaterialId}`);
  document.getElementById("relationship-list").innerHTML = links.slice(0, 14).map((item) => `<div class="row-card relationship-row"><span>${item.from}</span><strong>${titleCase(item.type)}</strong><span>${item.to}</span></div>`).join("");
  await loadGraphNodeInsight(state.selectedGraphNodeId);
  addActivityEvent("Graph updated", `Loaded ${graph.nodes.length} nodes and ${graph.edges.length} relationships.`, "graph");
}

async function loadGraphPath() {
  const sourceId = document.getElementById("graph-source").value;
  const targetId = document.getElementById("graph-target").value;
  const result = await fetchJson(`/graph/path?source_id=${sourceId}&target_id=${targetId}`);
  document.getElementById("graph-path-results").innerHTML = result.path.length
    ? result.path.map((node, index) => `<div class="row-card"><strong>${index + 1}. ${node.label}</strong><p>${titleCase(node.type)}</p></div>`).join("")
    : `<div class="row-card"><strong>No path found</strong><p>Try another source or target node.</p></div>`;
}

async function loadRecommendationsSummary() {
  const recommendations = await fetchJson("/query/recommendations?prioritize_sustainability=true");
  document.getElementById("hero-recommendations").textContent = recommendations.length;
}

async function runComparison() {
  const payload = {
    material_ids: selectedMaterialsFromCompare(),
    weights: {
      sustainability_score: Number(document.getElementById("weight-sustainability").value),
      recyclability_score: Number(document.getElementById("weight-recyclability").value),
      compostability_score: Number(document.getElementById("weight-compostability").value),
      oxygen_barrier: Number(document.getElementById("weight-barrier").value),
      moisture_barrier: Number(document.getElementById("weight-barrier").value),
      cost_efficiency: Number(document.getElementById("weight-cost").value),
    },
  };
  const results = await fetchJson("/materials/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.compareResults = results;
  document.getElementById("compare-results").innerHTML = results.length
    ? results.map((item, index) => `
      <div class="row-card compare-result-card compare-result-card-${index === 0 ? "leader" : index === 1 ? "challenger" : "fallback"}">
        <div class="compare-result-rank">${index === 0 ? "Leading option" : index === 1 ? "Strong alternative" : "Fallback option"}</div>
        <strong>${item.name}</strong>
        <p>Weighted score ${item.weighted_score}</p>
        <small>${index === 0 ? "Current leader based on active weights." : index === 1 ? "Closest alternative with a plausible tradeoff profile." : "Useful fallback if the leading options are blocked."}</small>
        <div class="tag-group">
          <span class="pill">Sustainability ${item.scores.sustainability}</span>
          <span class="pill">Recyclability ${item.scores.recyclability}</span>
          <span class="pill">Cost ${item.scores.cost_efficiency}</span>
        </div>
        <div class="action-row">
          <button type="button" class="mini-action" data-select-material="${escapeHtml(item.material_id)}">Open</button>
          <button type="button" class="mini-action" data-open-graph="${escapeHtml(item.material_id)}">Open in graph</button>
          <button type="button" class="mini-action" data-run-scenario="supplier_outage">Run scenario</button>
          <button type="button" class="mini-action" data-send-review="${escapeHtml(item.material_id)}" data-review-type="material_decision" data-review-label="${escapeHtml(item.name)}" data-review-reason="Comparison result needs human approval." data-review-context="Weighted score ${escapeHtml(String(item.weighted_score))}">Send to review</button>
          <button type="button" class="mini-action" data-export-material="${escapeHtml(item.material_id)}">Export</button>
        </div>
      </div>`).join("")
    : `<div class="row-card"><strong>No ranked output</strong><p>Select at least one shortlisted material and run the ranking.</p></div>`;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderComparisonMatrix(results);
  }
  syncActiveCase({
    shortlist_material_ids: payload.material_ids,
    status: "compare",
    workflow_step: "Compare",
    note: results[0] ? `Leading option ${results[0].name} at weighted score ${results[0].weighted_score}.` : state.activeCase?.note || "",
  }, { syncMemory: true });
  bindInlineActions();
}

async function loadGraphNodeInsight(nodeId) {
  const insight = await fetchJson(`/graph/node-insight?node_id=${encodeURIComponent(nodeId)}`);
  renderGraphNodeInsight(insight);
  if (insight.node.type === "supplier") {
    const supplier = await fetchJson(`/suppliers/${encodeURIComponent(nodeId)}`);
    renderSupplierDetail(supplier);
  } else {
    renderSupplierDetail(null);
  }
  if (insight.node.type === "regulation") {
    const regulation = await fetchJson(`/regulations/${encodeURIComponent(nodeId)}`);
    renderRegulationDetail(regulation);
  } else {
    renderRegulationDetail(null);
  }
}

function renderGraphNodeInsight(insight) {
  document.getElementById("insight-title").textContent = `${insight.node.label} (${titleCase(insight.node.type)})`;
  document.getElementById("insight-summary").textContent = insight.summary;
  document.getElementById("analytics-summary").innerHTML = (insight.metrics || [])
    .map((item) => `<div class="metric"><div class="value">${escapeHtml(item.value)}</div><div>${escapeHtml(item.label)}</div></div>`)
    .join("");
  const visuals = document.getElementById("analytics-visuals");
  if (visuals) {
    const confidence = Number((insight.metrics || []).find((item) => /confidence/i.test(item.label))?.value || 72);
    const exposure = Number((insight.metrics || []).find((item) => /risk|exposure/i.test(item.label))?.value || 48);
    const evidence = Number((insight.related || []).length ? Math.min(100, 32 + insight.related.length * 9) : 24);
    visuals.innerHTML = [
      { label: "Confidence", value: confidence, tone: confidence >= 75 ? "good" : confidence >= 50 ? "warn" : "risk", note: "Decision confidence from current graph context." },
      { label: "Exposure", value: exposure, tone: exposure >= 70 ? "risk" : exposure >= 45 ? "warn" : "good", note: "Higher values indicate more decision pressure." },
      { label: "Evidence", value: evidence, tone: evidence >= 70 ? "good" : evidence >= 45 ? "warn" : "risk", note: "Coverage signal based on nearby connected context." },
    ].map((item) => `
      <div class="signal-meter">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(String(item.value))}%</strong>
        <div class="signal-meter-track"><div class="signal-meter-fill signal-${escapeHtml(item.tone)}" style="width:${Math.max(0, Math.min(100, item.value))}%;"></div></div>
        <small>${escapeHtml(item.note)}</small>
      </div>`).join("");
  }

  document.getElementById("analytics-details").innerHTML = (insight.facts || []).length
    ? insight.facts.map((item) => `<div class="row-card"><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.value)}</p></div>`).join("")
    : `<div class="row-card"><strong>No additional details</strong><p>This node does not expose extra structured fields in the demo dataset.</p></div>`;

  const relationshipCards = [];
  (insight.relationship_counts || []).slice(0, 4).forEach((item) => {
    relationshipCards.push(`<div class="row-card"><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.value)} connected edges</p></div>`);
  });
  (insight.timeline || []).slice(0, 4).forEach((item) => {
    relationshipCards.push(`<div class="row-card"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p><small>${escapeHtml(item.meta || "")}</small></div>`);
  });
  document.getElementById("analytics-relationships").innerHTML = relationshipCards.length
    ? relationshipCards.join("")
    : `<div class="row-card"><strong>No recent signal</strong><p>This node currently has no timeline or relationship mix details.</p></div>`;

  document.getElementById("analytics-related").innerHTML = (insight.related || []).length
    ? `
      <table>
        <thead><tr><th>Connected node</th><th>Type</th><th>Relationship</th></tr></thead>
        <tbody>
        ${insight.related.map((item) => `
          <tr>
            <td><button type="button" class="table-link-button" data-node-id="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button></td>
            <td>${escapeHtml(titleCase(item.type))}</td>
            <td>${escapeHtml(titleCase(item.relationship))}</td>
          </tr>`).join("")}
        </tbody>
      </table>`
    : `<table><tbody><tr><td>No connected nodes available for this selection.</td></tr></tbody></table>`;

  document.querySelectorAll("#analytics-related [data-node-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      await selectGraphNode(button.dataset.nodeId);
    });
  });
}

async function selectGraphNode(nodeId) {
  state.selectedGraphNodeId = nodeId;
  const sourceSelect = document.getElementById("graph-source");
  if (sourceSelect) {
    sourceSelect.value = nodeId;
  }
  document.querySelectorAll(".graph-node").forEach((button) => {
    button.classList.toggle("active", button.dataset.nodeId === nodeId);
  });
  const node = state.currentGraph?.nodes?.find((item) => item.id === nodeId);
  if (node) {
    pushRecentEntity({ id: nodeId, label: node.label, type: node.type });
  }
  await loadGraphNodeInsight(nodeId);
}

async function loadAnalytics() {
  if (state.selectedGraphNodeId) {
    await loadGraphNodeInsight(state.selectedGraphNodeId);
  }
}

async function runGlobalSearch() {
  const input = document.getElementById("global-search-input");
  const imageInput = document.getElementById("global-search-image");
  const query = input.value.trim();
  const hasImage = Boolean(imageInput?.files?.length);
  if (!query && !hasImage) {
    setStatus("global-search-status", "Type something or upload an image.", "error");
    renderTableCard("global-search-results", [], [], "Search across materials, suppliers, regulations, documents, and reports.");
    renderRelatedDiscovery(null);
    return;
  }
  setStatus("global-search-status", hasImage ? "Identifying the uploaded image and checking the product knowledge base..." : "Searching the portfolio...", "info");
  state.latestGlobalSearch = query || imageInput.files[0]?.name || "";
  syncActiveCase({
    latest_search: state.latestGlobalSearch,
    status: "discover",
    workflow_step: "Discover",
  });
  let results = [];
  let related = null;
  let identification = null;

  if (hasImage || query) {
    const formData = new FormData();
    if (query) formData.append("query", query);
    if (hasImage) formData.append("image", imageInput.files[0]);
    const payload = await fetchJson("/search/discover", {
      method: "POST",
      body: formData,
    });
    results = payload.results || [];
    related = payload.related || null;
    identification = payload.identification || null;
  }

  const discoveredComponent = results.find((item) => item.entity_type === "component" && item.discovery_state === "newly_discovered");
  if (discoveredComponent && identification) {
    setStatus(
      "global-search-status",
      `${identification.label} was identified ${identification.method === "image_filename_inference" ? "from the uploaded image" : "from your search"} and saved on July 22, 2026 for future lookups.`,
      "success"
    );
  } else if (identification) {
    const basis = identification.method === "image_filename_inference" ? "Identified from the uploaded image" : "Matched from your search";
    setStatus("global-search-status", results.length ? `${basis} and found ${results.length} matching records.` : "No matches found.", results.length ? "success" : "info");
  } else {
    setStatus("global-search-status", results.length ? `Found ${results.length} matching records.` : "No matches found.", results.length ? "success" : "info");
  }
  renderTableCard(
    "global-search-results",
    [
      { label: "Type", render: (item) => `<span class="table-badge">${escapeHtml(formatEntityLabel(item.entity_type))}</span>` },
      { label: "Result", render: (item) => `<strong>${escapeHtml(item.title)}</strong><br /><small>${escapeHtml(item.subtitle)}</small>` },
      { label: "Context", render: (item) => escapeHtml(item.meta || "") },
      {
        label: "Actions",
        render: (item) => {
          if (item.entity_type === "material") {
            return `
              <div class="action-row">
                <button type="button" class="mini-action" data-select-material="${escapeHtml(item.entity_id)}">Open</button>
                <button type="button" class="mini-action" data-compare-material="${escapeHtml(item.entity_id)}">Compare</button>
                <button type="button" class="mini-action" data-shortlist-material="${escapeHtml(item.entity_id)}">Shortlist</button>
                <button type="button" class="mini-action" data-open-graph="${escapeHtml(item.entity_id)}">Graph</button>
                <button type="button" class="mini-action" data-send-review="${escapeHtml(item.entity_id)}" data-review-type="material_decision" data-review-label="${escapeHtml(item.title)}" data-review-reason="Global search surfaced a candidate for human review." data-review-context="${escapeHtml(item.meta || "")}">Review</button>
              </div>`;
          }
          if (item.entity_type === "supplier") {
            return `<div class="action-row"><button type="button" class="mini-action" data-open-supplier="${escapeHtml(item.entity_id)}">Open supplier</button><button type="button" class="mini-action" data-send-review="${escapeHtml(item.entity_id)}" data-review-type="supplier_review" data-review-label="${escapeHtml(item.title)}" data-review-reason="Supplier surfaced from global search for review." data-review-context="${escapeHtml(item.meta || "")}">Review</button></div>`;
          }
          if (item.entity_type === "regulation") {
            return `<div class="action-row"><button type="button" class="mini-action" data-open-regulation="${escapeHtml(item.entity_id)}">Open regulation</button></div>`;
          }
          if (item.entity_type === "component") {
            return `
              <div class="action-row">
                <button type="button" class="mini-action" data-ask-component="${escapeHtml(item.title)}">Ask workspace</button>
                ${item.source_url ? `<a class="mini-action link-action" href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">Open source</a>` : ""}
              </div>`;
          }
          const fallbackMaterial = item.entity_type === "report" || item.entity_type === "document" ? state.selectedMaterialId : "";
          return `<div class="action-row"><button type="button" class="mini-action" data-open-graph="${escapeHtml(fallbackMaterial)}">Open context</button>${item.entity_id ? `<button type="button" class="mini-action" data-open-evidence="${escapeHtml(item.entity_id)}">Open evidence</button>` : ""}</div>`;
        },
      },
    ],
    results,
    "Try a material family, supplier name, regulation title, evidence keyword, or upload a component image."
  );
  renderRelatedDiscovery(related);
  bindInlineActions();
}

function renderRelatedDiscovery(related) {
  const container = document.getElementById("global-search-related");
  if (!container) return;
  if (!related || (!related.materials?.length && !related.applications?.length && !related.components?.length)) {
    container.innerHTML = "";
    return;
  }
  const section = (title, items) => {
    if (!items.length) return "";
    return `
      <div class="detail-card">
        <h5>${escapeHtml(title)}</h5>
        <div class="card-list compact-list">
          ${items.join("")}
        </div>
      </div>`;
  };
  container.innerHTML = [
    section(
      "Related materials",
      (related.materials || []).map((item) => `<div class="row-card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.category)} | ${escapeHtml(item.compliance_state)}</p></div>`)
    ),
    section(
      "Related applications",
      (related.applications || []).map((item) => `<div class="row-card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.use_case)}</p></div>`)
    ),
    section(
      "Similar components",
      (related.components || []).map((item) => `<div class="row-card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.summary || "Cached component reference")}</p></div>`)
    ),
  ].join("");
}

function skeletonBlock(type) {
  if (type === "graph") {
    return `
      <div class="graph-skeleton-grid">
        <div class="skeleton skeleton-node"></div>
        <div class="skeleton skeleton-node"></div>
        <div class="skeleton skeleton-node"></div>
      </div>`;
  }
  return `
    <div class="skeleton-stack">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line short"></div>
      <div class="skeleton skeleton-card"></div>
    </div>`;
}

async function loadBenchmarks() {
  if (!document.getElementById("benchmark-status")) {
    return;
  }
  const data = await fetchJson("/benchmarks");
  const neo4jStatus = data.neo4j?.status || data.status || "not-run";
  document.getElementById("benchmark-status").innerHTML = `
    <div class="metric"><div class="value">${titleCase(neo4jStatus)}</div><div>Neo4j benchmark state</div></div>
    <div class="metric"><div class="value">${state.privateDataStatus.private_data_active ? "Active" : "Not loaded"}</div><div>Private data status</div></div>`;
  document.getElementById("benchmark-query-set").innerHTML = (data.query_set || []).map((item) => `<div class="row-card"><strong>${item.query}</strong><p>${item.note}</p></div>`).join("");
  document.getElementById("benchmark-plan-notes").innerHTML = (data.query_plan_notes || data.notes || []).map((item) => `<div class="row-card"><p>${item.note || item}</p></div>`).join("");
}

async function applyFilters() {
  const search = document.getElementById("filter-search").value.trim();
  const family = document.getElementById("filter-family").value.trim();
  const region = document.getElementById("filter-region").value;
  const category = document.getElementById("filter-category").value;
  const regulation = document.getElementById("filter-regulation").value;
  const claim = document.getElementById("filter-claim").value;
  const compliance = document.getElementById("filter-compliance").value;
  const performanceMetric = document.getElementById("filter-performance-metric").value;
  const performanceScore = document.getElementById("filter-performance-score").value;
  const supplierCapability = document.getElementById("filter-supplier-capability").value.trim();
  const sustainability = document.getElementById("filter-sustainability").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (family) params.set("material_family", family);
  if (region) params.set("region", region);
  if (category) params.set("category", category);
  if (regulation) params.set("regulation_id", regulation);
  if (claim) params.set("claim_type", claim);
  if (compliance) params.set("compliance_state", compliance);
  if (performanceMetric) params.set("performance_metric", performanceMetric);
  if (performanceScore) params.set("min_performance_score", performanceScore);
  if (supplierCapability) params.set("supplier_capability", supplierCapability);
  if (sustainability) params.set("min_sustainability", sustainability);
  const results = await fetchJson(`/materials/filter?${params.toString()}`);
  state.filteredMaterials = results;
  populateMaterialControls(results.length ? results : state.materials);
  document.getElementById("filter-results-summary").textContent = results.length ? `Showing ${results.length} filtered materials` : "No materials matched. Reverting to full portfolio.";
  if (!results.length) state.filteredMaterials = [];
  await refreshMaterialContext();
}

function updateExportLinks(material) {
  const supplierIds = (material.suppliers || []).map((item) => item.supplier_id).join(",");
  document.getElementById("export-executive-summary-pdf").href = `/exports/executive-summary.pdf?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-executive-summary-csv").href = `/exports/executive-summary.csv?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-compliance-pack-csv").href = `/exports/compliance-pack.csv?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-compliance-pack-pdf").href = `/exports/compliance-pack.pdf?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-supplier-snapshot-pdf").href = `/exports/supplier-comparison.pdf?supplier_ids=${encodeURIComponent(supplierIds)}`;
  document.getElementById("export-supplier-snapshot-csv").href = `/exports/supplier-comparison.csv?supplier_ids=${encodeURIComponent(supplierIds)}`;
  document.querySelectorAll(".export-link").forEach((link) => {
    link.dataset.materialId = material.material_id;
    link.dataset.materialName = material.name || material.material_id;
  });
}

function populateScenarioControls(material) {
  const supplierSelect = document.getElementById("scenario-supplier");
  const regulationSelect = document.getElementById("scenario-regulation");
  if (!supplierSelect || !regulationSelect) return;

  const suppliers = material?.suppliers || [];
  supplierSelect.innerHTML = `<option value="">Auto from selected material</option>${suppliers.map((item) => `<option value="${item.supplier_id}">${item.name}</option>`).join("")}`;
  regulationSelect.innerHTML = `<option value="">Next pending regulation</option>${(state.regulations || []).map((item) => `<option value="${item.regulation_id}">${item.name}</option>`).join("")}`;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.applyScenarioVisibility(document.getElementById("scenario-type")?.value || "supplier_outage");
  }
}

function formatScenarioMetricValue(value) {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "object") return escapeHtml(JSON.stringify(value));
  return escapeHtml(String(value));
}

function renderScenarioResult(result) {
  document.getElementById("scenario-summary").textContent = result.summary || "Scenario completed.";
  const metrics = result.metrics || {};
  document.getElementById("scenario-metrics").innerHTML = Object.keys(metrics).length
    ? Object.entries(metrics).map(([key, value]) => `<div class="metric"><div class="value">${formatScenarioMetricValue(value)}</div><div>${escapeHtml(titleCase(key))}</div></div>`).join("")
    : `<div class="metric"><div class="value">No metrics</div><div>Projected summary</div></div>`;

  document.getElementById("scenario-actions").innerHTML = (result.actions || []).length
    ? result.actions.map((item) => `<div class="row-card"><strong>${escapeHtml(item)}</strong></div>`).join("")
    : `<div class="row-card"><strong>No follow-up actions</strong><p>This scenario returned no recommended operational steps.</p></div>`;

  document.getElementById("scenario-impacts").innerHTML = (result.impacts || []).length
    ? result.impacts.map((item) => {
      const rows = Object.entries(item)
        .filter(([key]) => key !== "recommended_substitutes")
        .map(([key, value]) => `<div class="score-row"><span>${escapeHtml(titleCase(key))}</span><strong>${formatScenarioMetricValue(value)}</strong></div>`)
        .join("");
      const substitutes = Array.isArray(item.recommended_substitutes) && item.recommended_substitutes.length
        ? `<div class="tag-group">${item.recommended_substitutes.map((entry) => `<span class="pill">${escapeHtml(typeof entry === "string" ? entry : entry.name)}</span>`).join("")}</div>`
        : "";
      return `<div class="row-card">${rows}${substitutes}</div>`;
    }).join("")
    : `<div class="row-card"><strong>No impacted records</strong><p>This scenario did not change any material status in the current dataset.</p></div>`;
}

function renderSupplierDetail(supplier) {
  const container = document.getElementById("supplier-detail-panel");
  if (!container) return;
  if (!supplier) {
    container.innerHTML = skeletonBlock("detail");
    return;
  }
  const watchTone = supplier.disruption_risk_score >= 70 ? "risk" : supplier.disruption_risk_score >= 50 ? "warn" : "good";
  container.innerHTML = `
      <div class="detail-card">
        <h5>${escapeHtml(supplier.name)}</h5>
        <h4>${escapeHtml(supplier.country)} supplier profile</h4>
        <p class="panel-helper compact-helper">Use this view to understand whether the supplier is stable enough to support the current material path.</p>
      <div class="key-facts">
        <div class="fact"><span>Lead time</span><strong>${escapeHtml(supplier.lead_time_days)} days</strong></div>
        <div class="fact"><span>Risk</span><strong>${escapeHtml(supplier.disruption_risk_score)}</strong></div>
        <div class="fact"><span>ESG</span><strong>${escapeHtml(supplier.esg_score)}</strong></div>
        <div class="fact"><span>Materials</span><strong>${escapeHtml(supplier.supplied_materials.length)}</strong></div>
      </div>
        <div class="trend-chip-grid">
          ${(supplier.certifications_detail || []).map((item) => `<span class="trend-chip">${escapeHtml(item.name)}</span>`).join("")}
        </div>
        <div class="analytics-visuals">
          <div class="signal-meter"><span>Risk score</span><strong>${escapeHtml(String(supplier.disruption_risk_score))}</strong><div class="signal-meter-track"><div class="signal-meter-fill signal-${watchTone}" style="width:${Math.min(100, supplier.disruption_risk_score)}%;"></div></div><small>Watchlist state for the current supplier profile.</small></div>
          <div class="signal-meter"><span>Lead time</span><strong>${escapeHtml(String(supplier.lead_time_days))}d</strong><div class="signal-meter-track"><div class="signal-meter-fill signal-${supplier.lead_time_days > 45 ? "risk" : supplier.lead_time_days > 28 ? "warn" : "good"}" style="width:${Math.min(100, supplier.lead_time_days)}%;"></div></div><small>Operational responsiveness indicator.</small></div>
          <div class="signal-meter"><span>ESG</span><strong>${escapeHtml(String(supplier.esg_score))}</strong><div class="signal-meter-track"><div class="signal-meter-fill signal-${supplier.esg_score >= 75 ? "good" : supplier.esg_score >= 55 ? "warn" : "risk"}" style="width:${Math.min(100, supplier.esg_score)}%;"></div></div><small>Sustainability and governance signal.</small></div>
        </div>
      </div>
      <div class="detail-card">
        <h5>Trend signal</h5>
        <h4>Risk and lead-time movement</h4>
      <div class="timeline-chart-footer">
        <span>${(supplier.risk_trend || []).map((item) => `${item.quarter}: risk ${item.risk_score}`).join(" | ") || "No risk trend available."}</span>
      </div>
      <div class="timeline-chart-footer">
        <span>${(supplier.lead_time_trend || []).map((item) => `${item.quarter}: ${item.lead_time_days}d`).join(" | ") || "No lead-time trend available."}</span>
      </div>
      <div class="subsection-heading">Action summary</div>
      <div class="card-list compact-list">
        <div class="row-card"><strong>Use when</strong><p>Supply remains qualified but risk needs monitoring against regulation timing or cost pressure.</p></div>
        <div class="row-card"><strong>Watch for</strong><p>Lead-time expansion, certification expiry, or supplier concentration across shortlisted materials.</p></div>
      </div>
      <div class="subsection-heading">Supplied materials</div>
      <div class="card-list compact-list">
        ${(supplier.supplied_materials || []).slice(0, 6).map((item) => `<div class="row-card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.category)} | ${escapeHtml(item.compliance_state)}</p></div>`).join("")}
      </div>
    </div>`;
}

function renderRegulationDetail(regulation) {
  const container = document.getElementById("regulation-detail-panel");
  if (!container) return;
  if (!regulation) {
    container.innerHTML = skeletonBlock("detail");
    return;
  }
  const exposureScore = Math.min(100, (regulation.affected_materials?.length || 0) * 18);
  container.innerHTML = `
      <div class="detail-card">
        <h5>${escapeHtml(regulation.name)}</h5>
        <h4>${regulation.active ? "Active" : "Upcoming"} regulation</h4>
        <p class="panel-helper compact-helper">Use this panel to understand which materials are exposed, what evidence is missing, and what action should happen next.</p>
      <div class="key-facts">
          <div class="fact"><span>Effective date</span><strong>${escapeHtml(regulation.effective_date)}</strong></div>
          <div class="fact"><span>Focus</span><strong>${escapeHtml(titleCase(regulation.focus))}</strong></div>
          <div class="fact"><span>Affected materials</span><strong>${escapeHtml(regulation.affected_materials.length)}</strong></div>
        </div>
        <div class="analytics-visuals">
          <div class="signal-meter"><span>Exposure</span><strong>${escapeHtml(String(exposureScore))}%</strong><div class="signal-meter-track"><div class="signal-meter-fill signal-${exposureScore >= 70 ? "risk" : exposureScore >= 45 ? "warn" : "good"}" style="width:${exposureScore}%;"></div></div><small>Exposure estimate based on linked materials.</small></div>
          <div class="signal-meter"><span>Evidence gaps</span><strong>${escapeHtml(String((regulation.evidence_gaps || []).length))}</strong><div class="signal-meter-track"><div class="signal-meter-fill signal-${(regulation.evidence_gaps || []).length > 2 ? "risk" : (regulation.evidence_gaps || []).length ? "warn" : "good"}" style="width:${Math.min(100, ((regulation.evidence_gaps || []).length * 25))}%;"></div></div><small>Missing support before final approval.</small></div>
          <div class="signal-meter"><span>Watchlist</span><strong>${regulation.active ? "Active" : "Upcoming"}</strong><div class="signal-meter-track"><div class="signal-meter-fill signal-${regulation.active ? "risk" : "warn"}" style="width:${regulation.active ? 90 : 60}%;"></div></div><small>Urgency relative to the current decision window.</small></div>
        </div>
      </div>
      <div class="detail-card">
        <h5>Action context</h5>
      <h4>Evidence gaps and next actions</h4>
      <div class="card-list compact-list">
        ${(regulation.evidence_gaps || []).length
          ? regulation.evidence_gaps.map((item) => `<div class="row-card"><strong>Evidence gap</strong><p>${escapeHtml(item)}</p></div>`).join("")
          : `<div class="row-card"><strong>No immediate gaps</strong><p>Linked material dossiers look reasonably complete in the current dataset.</p></div>`}
      </div>
      <div class="card-list compact-list">
        ${(regulation.likely_actions || []).map((item) => `<div class="row-card"><strong>Likely action</strong><p>${escapeHtml(item)}</p></div>`).join("")}
      </div>
    </div>`;
}

async function runScenario() {
  document.getElementById("scenario-summary").textContent = "Running scenario and calculating impacts...";
  const payload = {
    scenario: document.getElementById("scenario-type").value,
    material_id: state.selectedMaterialId,
    supplier_id: document.getElementById("scenario-supplier").value || null,
    options: {
      scenario_type: document.getElementById("scenario-type").value,
      scope: document.getElementById("scenario-scope").value,
      regulation_id: document.getElementById("scenario-regulation").value || null,
      metric: document.getElementById("scenario-metric").value,
      target_value: Number(document.getElementById("scenario-target-value").value || 0),
      max_cost: Number(document.getElementById("scenario-max-cost").value || 0),
      percent_increase: Number(document.getElementById("scenario-percent-increase").value || 0),
    },
  };
  const result = await fetchJson("/query/scenario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderScenarioResult(result);
  state.scenarioComparisons = [
    ...state.scenarioComparisons.slice(-1),
    {
      scenario: payload.scenario,
      before: { material_id: payload.material_id, supplier_id: payload.supplier_id, options: payload.options },
      summary: result.summary,
      metrics: result.metrics || {},
    },
  ];
  renderScenarioComparison();
  syncActiveCase({
    scenario_type: payload.scenario,
    status: "validate",
    workflow_step: "Validate",
    note: result.summary || state.activeCase?.note || "",
  }, { syncMemory: true });
  addActivityEvent("Scenario run", result.summary || titleCase(payload.scenario), "scenario");
  await Promise.all([loadScenarioHistory(), loadOperationsDashboard()]);
}

async function loadTrendCharts() {
  state.analyticsOverview = await fetchJson("/analytics/overview");
  if (window.PackGraphTrendCharts) {
    window.PackGraphTrendCharts.renderOverview(state.analyticsOverview);
  }
}

async function loadMaterialTimeline() {
  const timeline = await fetchJson(`/materials/${state.selectedMaterialId}/timeline`);
  if (window.PackGraphTrendCharts) {
    window.PackGraphTrendCharts.renderMaterialTimeline(timeline);
  }
}

async function saveInvestigation() {
  const title = document.getElementById("investigation-title").value.trim();
  if (!title) {
    setStatus("investigation-status", "Add a title before saving the investigation.", "error");
    return;
  }
  setStatus("investigation-status", "Saving investigation context...", "info");
  const payload = {
    title,
    focus_material_id: state.selectedMaterialId,
    notes: document.getElementById("investigation-notes").value.trim(),
    shortlisted_material_ids: selectedMaterialsFromCompare(),
    comparison_material_ids: state.compareResults.map((item) => item.material_id),
    decision_rationale: document.getElementById("investigation-rationale").value.trim(),
    status: "open",
    project_status: document.getElementById("investigation-project-status").value,
    owner_name: document.getElementById("investigation-owner").value.trim(),
    due_date: document.getElementById("investigation-due-date").value || null,
  };
  const method = state.currentInvestigationId ? "PATCH" : "POST";
  const url = state.currentInvestigationId ? `/investigations/${state.currentInvestigationId}` : "/investigations";
  try {
    const result = await fetchJson(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    clearDraft(DRAFT_STORAGE_KEYS.investigation);
    state.currentInvestigationId = result.investigation_id;
    setStatus("investigation-status", `Saved ${result.title} with ${result.shortlisted_material_ids.length} shortlisted materials.`, "success");
    syncActiveCase({
      name: result.title,
      note: result.decision_rationale || result.notes || state.activeCase?.note || "",
      status: "review",
      workflow_step: "Review",
      review_state: result.project_status || "active",
      next_action_label: "Export or send for approval",
      next_action_target: "workbench",
      next_action_reason: "The shortlist and rationale are saved. Finish approval or export the case package.",
    }, { syncMemory: true });
    await loadInvestigations();
  } catch (error) {
    setStatus("investigation-status", error.message, "error");
  }
}

async function resumeInvestigation(investigationId) {
  const investigation = await fetchJson(`/investigations/${investigationId}`);
  state.currentInvestigationId = investigation.investigation_id;
  document.getElementById("investigation-title").value = investigation.title || "";
  document.getElementById("investigation-project-status").value = investigation.project_status || "active";
  document.getElementById("investigation-owner").value = investigation.owner_name || "";
  document.getElementById("investigation-due-date").value = investigation.due_date || "";
  document.getElementById("investigation-notes").value = investigation.notes || "";
  document.getElementById("investigation-rationale").value = investigation.decision_rationale || "";
  if (investigation.focus_material_id) {
    state.selectedMaterialId = investigation.focus_material_id;
    document.getElementById("material-select").value = state.selectedMaterialId;
  }
  const compare = document.getElementById("compare-materials");
  Array.from(compare.options).forEach((option) => {
    option.selected = (investigation.shortlisted_material_ids || []).includes(option.value);
  });
  renderCompareSelectionSummary();
  await refreshMaterialContext();
  await runComparison();
  syncActiveCase({
    name: investigation.title,
    note: investigation.decision_rationale || investigation.notes || "",
    shortlist_material_ids: investigation.shortlisted_material_ids || [],
    focus_material_id: investigation.focus_material_id || state.selectedMaterialId,
    status: "compare",
    workflow_step: "Compare",
    review_state: investigation.project_status || investigation.status || "active",
    next_action_label: "Resume comparison",
    next_action_target: "workbench",
    next_action_reason: "Continue comparing shortlisted materials, validate evidence, or move the case toward approval.",
  });
  setStatus("investigation-status", `Resumed ${investigation.title}.`, "success");
}

async function resumeWorkspace(workspaceId) {
  const workspace = state.workspaces.find((item) => item.workspace_id === workspaceId);
  if (!workspace) return;
  state.currentPage = workspace.active_tab || "overview";
  setPage(state.currentPage);
  if ((workspace.selected_material_ids || []).length) {
    state.selectedMaterialId = workspace.selected_material_ids[0];
  }
  const filters = workspace.filters || {};
  const mapping = {
    "filter-search": filters.search || "",
    "filter-family": filters.material_family || "",
    "filter-region": filters.region || "",
    "filter-category": filters.category || "",
    "filter-regulation": filters.regulation_id || "",
    "filter-claim": filters.claim_type || "",
    "filter-compliance": filters.compliance_state || "",
    "filter-performance-metric": filters.performance_metric || "",
    "filter-performance-score": filters.min_performance_score || "",
    "filter-supplier-capability": filters.supplier_capability || "",
    "filter-sustainability": filters.min_sustainability || "",
  };
  Object.entries(mapping).forEach(([id, value]) => {
    const element = document.getElementById(id);
    if (element) element.value = value;
  });
  state.graphFilter = filters.graph_filter || "all";
  state.graphPreset = filters.graph_preset || "full";
  state.graphIsolateSelection = Boolean(filters.graph_isolate_selection);
  state.graphCollapsedTypes = Array.isArray(filters.graph_collapsed_types) ? filters.graph_collapsed_types : [];
  state.graphPinnedNodeIds = Array.isArray(filters.graph_pinned_node_ids) ? filters.graph_pinned_node_ids : [];
  persistGraphUiState();
  await applyFilters();
  const compare = document.getElementById("compare-materials");
  Array.from(compare.options).forEach((option) => {
    option.selected = (workspace.selected_material_ids || []).includes(option.value);
  });
  renderCompareSelectionSummary();
  await runComparison();
  syncActiveCase({
    name: workspace.name || "Saved workspace",
    shortlist_material_ids: workspace.selected_material_ids || [],
    focus_material_id: state.selectedMaterialId,
    status: "discover",
    workflow_step: "Discover",
  });
}

function setupPageNavigation() {
  document.querySelectorAll(".page-link").forEach((button) => {
    button.addEventListener("click", () => setPage(button.dataset.page));
  });
}

function setupShellNavigation() {
  document.querySelectorAll(".shell-link").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = button.dataset.section;
      setSection(target);
      if (target === "explore") {
        await loadExploreEntities();
      } else if (target === "contribute") {
        await loadContributionData();
      } else if (target === "community") {
        await loadCommunityData();
      }
    });
  });
}

function scrollToTarget(targetId) {
  if (!targetId) return;
  const target = document.getElementById(targetId);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setupNavigation() {
  document.getElementById("jump-chat").addEventListener("click", () => {
    window.PackGraphChat?.open();
  });
  document.getElementById("jump-workbench").addEventListener("click", () => {
    setPage("workbench");
    document.querySelector('[data-page="workbench"]').scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.querySelectorAll("[data-jump-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.jumpPage;
      setPage(target);
      document.querySelector(`[data-page="${target}"]`).scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  document.querySelectorAll("[data-scroll-target]").forEach((button) => {
    button.addEventListener("click", () => {
      scrollToTarget(button.dataset.scrollTarget);
      const nav = button.closest(".page-local-nav");
      if (nav) {
        nav.querySelectorAll(".page-local-link").forEach((link) => link.classList.toggle("active", link === button));
      }
    });
  });
}

function setupGraphZoomControls() {
  const zoomIn = document.getElementById("graph-zoom-in");
  const zoomOut = document.getElementById("graph-zoom-out");
  const canvas = document.getElementById("graph-subgraph");
  if (zoomIn) {
    zoomIn.addEventListener("click", () => {
      state.graphZoom = clamp(Number((state.graphZoom + 0.1).toFixed(2)), 0.7, 1.8);
      applyGraphZoom();
    });
  }
  if (zoomOut) {
    zoomOut.addEventListener("click", () => {
      state.graphZoom = clamp(Number((state.graphZoom - 0.1).toFixed(2)), 0.7, 1.8);
      applyGraphZoom();
    });
  }
  if (canvas) {
    canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const delta = event.deltaY < 0 ? 0.08 : -0.08;
        state.graphZoom = clamp(Number((state.graphZoom + delta).toFixed(2)), 0.7, 1.8);
        applyGraphZoom();
      },
      { passive: false }
    );
  }
  applyGraphZoom();
}

function setupGraphPanControls() {
  const canvas = document.getElementById("graph-subgraph");
  if (!canvas) return;

  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  const stopDragging = () => {
    dragging = false;
    canvas.classList.remove("dragging");
  };

  canvas.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    if (event.target.closest(".graph-node, .graph-zoom-controls button")) return;
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.classList.add("dragging");
  });

  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    const deltaX = event.clientX - lastX;
    const deltaY = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    state.graphPan.x = clamp(state.graphPan.x + deltaX, -240, 240);
    state.graphPan.y = clamp(state.graphPan.y + deltaY, -180, 180);
    applyGraphZoom();
  });

  window.addEventListener("mouseup", stopDragging);
  canvas.addEventListener("mouseleave", () => {
    if (dragging) {
      canvas.classList.add("dragging");
    }
  });
}

function setupGraphFilters() {
  const relationshipFilter = document.getElementById("graph-relationship-filter");
  const preset = document.getElementById("graph-preset");
  const isolate = document.getElementById("graph-isolate-selection");
  const reset = document.getElementById("graph-reset-view");
  const collapse = document.getElementById("graph-collapse-branch");
  const expand = document.getElementById("graph-expand-branch");
  const pin = document.getElementById("graph-pin-node");
  const evidence = document.getElementById("graph-open-evidence");
  const compare = document.getElementById("graph-compare-node");
  const saveView = document.getElementById("graph-save-view");
  if (relationshipFilter) {
    relationshipFilter.addEventListener("change", () => {
      state.graphFilter = relationshipFilter.value;
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  }
  if (preset) {
    preset.addEventListener("change", () => {
      state.graphPreset = preset.value;
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  }
  if (isolate) {
    isolate.addEventListener("click", () => {
      state.graphIsolateSelection = !state.graphIsolateSelection;
      isolate.textContent = state.graphIsolateSelection ? "Show full graph" : "Isolate branch";
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  }
  if (reset) {
    reset.addEventListener("click", () => {
      state.graphPan = { x: 0, y: 0 };
      state.graphZoom = 1;
      state.graphFilter = "all";
      state.graphPreset = "full";
      state.graphIsolateSelection = false;
      state.graphCollapsedTypes = [];
      state.graphPinnedNodeIds = [];
      if (relationshipFilter) relationshipFilter.value = "all";
      if (preset) preset.value = "full";
      if (isolate) isolate.textContent = "Isolate branch";
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
      persistGraphUiState();
      applyGraphZoom();
    });
  }
  document.querySelectorAll("[data-graph-chip]").forEach((button) => {
    button.addEventListener("click", () => {
      state.graphFilter = button.dataset.graphChip;
      const select = document.getElementById("graph-relationship-filter");
      if (select) select.value = state.graphFilter;
      document.querySelectorAll("[data-graph-chip]").forEach((chip) => chip.classList.toggle("active", chip === button));
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  });
  collapse?.addEventListener("click", () => {
    const type = selectedGraphBranchType();
    if (!type || state.graphCollapsedTypes.includes(type)) return;
    state.graphCollapsedTypes = [...state.graphCollapsedTypes, type];
    persistGraphUiState();
    if (state.currentGraph) renderGraphCanvas(state.currentGraph);
  });
  expand?.addEventListener("click", () => {
    const type = selectedGraphBranchType();
    if (!type) return;
    state.graphCollapsedTypes = state.graphCollapsedTypes.filter((item) => item !== type);
    persistGraphUiState();
    if (state.currentGraph) renderGraphCanvas(state.currentGraph);
  });
  pin?.addEventListener("click", () => {
    if (!state.selectedGraphNodeId) return;
    if (state.graphPinnedNodeIds.includes(state.selectedGraphNodeId)) {
      state.graphPinnedNodeIds = state.graphPinnedNodeIds.filter((item) => item !== state.selectedGraphNodeId);
    } else {
      state.graphPinnedNodeIds = [...state.graphPinnedNodeIds, state.selectedGraphNodeId];
    }
    persistGraphUiState();
    updateGraphActionBar();
    if (state.currentGraph) renderGraphCanvas(state.currentGraph);
  });
  evidence?.addEventListener("click", async () => {
    const node = selectedGraphNodeRecord();
    if (!node) return;
    if (node.type === "document" || node.type === "test_report" || node.type === "report") {
      setPage("workbench");
      await loadDocumentPreview(node.id);
      return;
    }
    if (node.type === "supplier") {
      await openSupplierProfile(node.id);
      return;
    }
    if (node.type === "regulation") {
      await openRegulationDetail(node.id);
      return;
    }
    setPage("workbench");
    await loadProvenance();
  });
  compare?.addEventListener("click", async () => {
    const node = selectedGraphNodeRecord();
    if (!node || node.type !== "material") return;
    addMaterialToShortlist(node.id);
    setPage("workbench");
    await runComparison();
  });
  saveView?.addEventListener("click", async () => {
    const workspaceName = document.getElementById("workspace-name");
    if (workspaceName && !workspaceName.value.trim()) {
      workspaceName.value = `Graph view ${new Date().toISOString().slice(0, 10)}`;
    }
    document.getElementById("workspace-form")?.requestSubmit();
  });
}

function setupForms() {
  const debouncedExploreReload = debounce(() => {
    loadExploreEntities();
  }, 280);
  const debouncedExploreAutocomplete = debounce((value) => {
    updateExploreAutocomplete(value);
  }, 180);
  const debouncedCommandCenterSearch = debounce(() => {
    runCommandCenter();
  }, 220);
  const debouncedGlobalSearch = debounce(() => {
    runGlobalSearch();
  }, 260);

  document.addEventListener("keydown", (event) => {
    const isCommandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
    if (isCommandShortcut) {
      event.preventDefault();
      openCommandCenter();
      document.getElementById("command-center-input")?.focus();
    }
    if (event.key === "Escape") {
      closeCommandCenter();
    }
  });

  document.getElementById("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const user = await fetchJson("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById("auth-email").value.trim(),
          password: document.getElementById("auth-password").value,
        }),
      });
      state.currentUser = user;
      setSessionToken(user.session_token);
      if (window.PackGraphAuthShell) {
        window.PackGraphAuthShell.renderUser(user);
      }
      setStatus("auth-status", `Signed in as ${user.name}.`, "success");
      await Promise.all([loadSavedSearches(), loadNotifications(), loadWorkspaces(), loadReviewQueue()]);
    } catch (error) {
      setStatus("auth-status", error.message, "error");
    }
  });

  document.getElementById("auth-register").addEventListener("click", async () => {
    try {
      const user = await fetchJson("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "New Explorer",
          email: document.getElementById("auth-email").value.trim() || `explorer${Date.now()}@packgraph.local`,
          password: document.getElementById("auth-password").value || "packgraph-demo",
          role_id: "explorer",
        }),
      });
      state.currentUser = user;
      setSessionToken(user.session_token);
      if (window.PackGraphAuthShell) {
        window.PackGraphAuthShell.renderUser(user);
      }
      setStatus("auth-status", `Created local account for ${user.name}.`, "success");
      await Promise.all([loadSavedSearches(), loadNotifications(), loadWorkspaces(), loadReviewQueue()]);
    } catch (error) {
      setStatus("auth-status", error.message, "error");
    }
  });

  document.getElementById("auth-logout").addEventListener("click", async () => {
    await fetchJson("/auth/logout", { method: "POST" });
    state.currentUser = null;
    setSessionToken("");
    if (window.PackGraphAuthShell) {
      window.PackGraphAuthShell.renderUser(null);
      window.PackGraphAuthShell.renderNotifications([]);
    }
    state.reviewQueue = [];
    state.reviewSummary = { total: 0, pending: 0 };
    renderReviewQueue();
    setStatus("auth-status", "Signed out of the local session.", "info");
  });

  document.getElementById("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = document.getElementById("question-input").value.trim();
    if (!question) return;
    const response = await fetchJson("/query/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        options: { material_id: state.selectedMaterialId, prioritize_sustainability: true },
        context: window.PackGraphChat?.getContext?.() || buildMaterialChatContext(state.selectedMaterialDetail),
      }),
    });
    handleChatResult(question, response);
    await Promise.all([loadReviewQueue(), loadNotifications()]);
  });

  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      document.getElementById("question-input").value = button.dataset.prompt;
      document.getElementById("ask-form").requestSubmit();
    });
  });

  document.getElementById("filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await applyFilters();
  });

  document.getElementById("compare-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runComparison();
  });

  document.getElementById("compare-materials").addEventListener("change", () => {
    renderCompareSelectionSummary();
    syncActiveCase({
      shortlist_material_ids: selectedMaterialsFromCompare(),
      status: "compare",
      workflow_step: "Compare",
    });
  });

  document.getElementById("document-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("document-search-input").value.trim();
    await loadProvenance(query);
  });

  document.getElementById("document-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await uploadDocumentEvidence();
  });

  document.getElementById("source-intake-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await uploadSourceIntake();
  });

  document.getElementById("scenario-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runScenario();
  });

  document.getElementById("scenario-type").addEventListener("change", (event) => {
    if (window.PackGraphWorkbenchPanels) {
      window.PackGraphWorkbenchPanels.applyScenarioVisibility(event.target.value);
    }
  });

  document.getElementById("graph-path-button").addEventListener("click", async () => {
    await loadGraphPath();
  });

  document.getElementById("investigation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveInvestigation();
  });

  document.getElementById("investigation-clear").addEventListener("click", () => {
    state.currentInvestigationId = null;
    document.getElementById("investigation-title").value = "";
    document.getElementById("investigation-project-status").value = "active";
    document.getElementById("investigation-owner").value = "";
    document.getElementById("investigation-due-date").value = "";
    document.getElementById("investigation-notes").value = "";
    document.getElementById("investigation-rationale").value = "";
    clearDraft(DRAFT_STORAGE_KEYS.investigation);
    setStatus("investigation-status", "Cleared the current investigation draft.", "info");
  });

  document.getElementById("case-sync").addEventListener("click", async () => {
    await syncProjectMemory({
      saved_entities: [state.activeCase?.focus_material_id],
      compared_entities: state.activeCase?.shortlist_material_ids || [],
      prior_questions: [state.activeCase?.latest_question],
      investigation_notes: [state.activeCase?.note],
      user_assumptions: [state.activeCase?.workflow_step],
    });
    setStatus("case-status", "Synced the active case to project memory.", "success");
  });

  document.getElementById("case-reset").addEventListener("click", () => {
    state.activeCase = defaultActiveCase();
    persistActiveCase();
    renderCaseWorkspace();
    renderWorkflowMap();
    renderCrossPageContext();
    setStatus("case-status", "Reset the active case workspace.", "info");
  });

  document.getElementById("workspace-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("workspace-name").value.trim();
    if (!name) {
      setStatus("workspace-status", "Add a workspace name before saving.", "error");
      return;
    }
    setStatus("workspace-status", "Saving workspace context...", "info");
    const payload = {
      name,
      filters: {
        search: document.getElementById("filter-search").value.trim(),
        material_family: document.getElementById("filter-family").value.trim(),
        region: document.getElementById("filter-region").value,
        category: document.getElementById("filter-category").value,
        regulation_id: document.getElementById("filter-regulation").value,
        claim_type: document.getElementById("filter-claim").value,
        compliance_state: document.getElementById("filter-compliance").value,
        performance_metric: document.getElementById("filter-performance-metric").value,
        min_performance_score: document.getElementById("filter-performance-score").value,
        supplier_capability: document.getElementById("filter-supplier-capability").value.trim(),
        min_sustainability: document.getElementById("filter-sustainability").value,
        graph_filter: state.graphFilter,
        graph_preset: state.graphPreset,
        graph_isolate_selection: state.graphIsolateSelection,
        graph_collapsed_types: state.graphCollapsedTypes,
        graph_pinned_node_ids: state.graphPinnedNodeIds,
        active_case_name: state.activeCase?.name || "",
        preset_type: document.getElementById("workspace-preset-type")?.value || "case",
        supplier_id: state.activeCase?.focus_supplier_id || state.latestSupplierId || "",
        investigation_id: state.currentInvestigationId || "",
        evidence_strength: state.activeCase?.evidence_strength || "unknown",
        review_state: state.activeCase?.review_state || "not_requested",
      },
      selected_material_ids: selectedMaterialsFromCompare().length ? selectedMaterialsFromCompare() : [state.selectedMaterialId],
      active_tab: state.currentPage,
    };
    const optimistic = {
      workspace_id: `local-workspace-${Date.now()}`,
      name,
      filters: payload.filters,
      selected_material_ids: payload.selected_material_ids,
      active_tab: payload.active_tab,
      pending: true,
    };
    state.workspaces = [optimistic, ...(state.workspaces || [])].slice(0, 12);
    renderSavedWorkspaces();
    try {
      await fetchJson("/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      document.getElementById("workspace-name").value = "";
      await Promise.all([loadWorkspaces(), loadNotifications()]);
      setStatus("workspace-status", `Saved workspace ${name}.`, "success");
      addActivityEvent("Saved workspace preset", name, payload.filters.preset_type || "workspace");
      syncActiveCase({
        name,
        shortlist_material_ids: payload.selected_material_ids,
        focus_material_id: state.selectedMaterialId,
        status: "discover",
        workflow_step: "Discover",
      }, { syncMemory: true });
    } catch (error) {
      state.workspaces = (state.workspaces || []).filter((item) => item.workspace_id !== optimistic.workspace_id);
      renderSavedWorkspaces();
      setStatus("workspace-status", error.message, "error");
    }
  });

  document.getElementById("command-center-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runCommandCenter();
  });
  document.getElementById("command-center-input").addEventListener("input", () => {
    const value = document.getElementById("command-center-input").value.trim();
    if (value.length >= 2) {
      debouncedCommandCenterSearch();
    }
  });

  document.getElementById("command-center-close").addEventListener("click", () => {
    closeCommandCenter();
  });

  document.getElementById("command-center-notifications").addEventListener("click", () => {
    openCommandCenter();
    document.getElementById("command-center-results").innerHTML = `
      <div class="command-center-group">
        <h4>Notification center</h4>
        <div id="command-center-notification-list" class="card-list compact-list"></div>
      </div>`;
    const list = document.getElementById("command-center-notification-list");
    list.innerHTML = (state.notifications || []).length
      ? state.notifications.map((item) => `<div class="row-card"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.detail)}</small></div>`).join("")
      : `<div class="row-card"><p>No notifications right now.</p></div>`;
  });

  document.querySelectorAll("[data-notification-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      setNotificationFilter(button.dataset.notificationFilter);
    });
  });

  document.getElementById("bookmark-current-entity").addEventListener("click", () => {
    const graphNode = selectedGraphNodeRecord();
    if (graphNode) {
      addBookmark({ id: graphNode.id, label: graphNode.label, type: graphNode.type });
      return;
    }
    const material = state.materials.find((item) => item.material_id === state.selectedMaterialId);
    if (material) {
      addBookmark({ id: material.material_id, label: material.name, type: "material" });
    }
  });

  document.getElementById("productivity-note").addEventListener("input", (event) => {
    state.personalWorkspace.quick_note = event.target.value.trim();
    persistPersonalWorkspace();
    renderPersonalWorkspace();
  });

  document.getElementById("add-productivity-reminder").addEventListener("click", () => {
    const input = document.getElementById("productivity-reminder");
    const value = input.value.trim();
    if (!value) return;
    state.personalWorkspace.reminders = [...(state.personalWorkspace.reminders || []), value].slice(-8);
    input.value = "";
    persistPersonalWorkspace();
    renderPersonalWorkspace();
  });

  document.getElementById("global-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runGlobalSearch();
  });
  document.getElementById("global-search-input").addEventListener("input", () => {
    const value = document.getElementById("global-search-input").value.trim();
    if (value.length >= 2) {
      debouncedGlobalSearch();
    }
  });

  document.getElementById("global-search-image-trigger").addEventListener("click", () => {
    document.getElementById("global-search-image").click();
  });

  document.getElementById("global-search-image").addEventListener("change", (event) => {
    const label = document.getElementById("global-search-image-label");
    const file = event.target.files?.[0];
    label.textContent = file ? `Selected image: ${file.name}` : "No image selected.";
  });

  document.getElementById("review-assign-self").addEventListener("click", async () => {
    await assignSelectedReviewToCurrentUser();
  });

  document.getElementById("review-approve").addEventListener("click", async () => {
    await applyReviewDecision("approved");
  });

  document.getElementById("review-reject").addEventListener("click", async () => {
    await applyReviewDecision("rejected");
  });

  document.getElementById("save-explore-search").addEventListener("click", async () => {
    try {
      await saveCurrentExploreSearch();
    } catch (error) {
      setStatus("explore-status", error.message, "error");
    }
  });

  document.getElementById("explore-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    document.getElementById("explore-hero-input").value = document.getElementById("explore-search").value;
    await loadExploreEntities();
  });

  document.getElementById("explore-sort").addEventListener("change", async () => {
    await loadExploreEntities();
  });
  ["explore-taxonomy", "explore-region", "explore-category", "explore-supplier", "explore-application", "explore-compliance", "explore-sustainability"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", debouncedExploreReload);
  });

  document.getElementById("explore-reset").addEventListener("click", async () => {
    document.getElementById("explore-filter-form").reset();
    document.getElementById("explore-hero-input").value = "";
    document.getElementById("explore-autocomplete").innerHTML = "";
    await loadExploreEntities();
  });

  document.getElementById("explore-hero-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = document.getElementById("explore-hero-input").value.trim();
    document.getElementById("explore-search").value = value;
    await loadExploreEntities();
  });

  document.getElementById("explore-hero-input").addEventListener("input", async (event) => {
    const value = event.target.value;
    document.getElementById("explore-search").value = value;
    debouncedExploreAutocomplete(value);
  });
  document.getElementById("explore-search").addEventListener("input", (event) => {
    document.getElementById("explore-hero-input").value = event.target.value;
    debouncedExploreReload();
  });

  document.getElementById("explore-hero-clear").addEventListener("click", async () => {
    document.getElementById("explore-hero-input").value = "";
    document.getElementById("explore-search").value = "";
    document.getElementById("explore-autocomplete").innerHTML = "";
    await loadExploreEntities();
  });

  document.getElementById("contribution-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitContribution();
  });

  document.getElementById("contribution-role").addEventListener("change", (event) => {
    state.selectedContributionRoleId = event.target.value;
    renderContributionRoleDetail();
    if (window.PackGraphContributePage) {
      window.PackGraphContributePage.renderRoles(state.contributionRoles, state.selectedContributionRoleId, (roleId) => {
        state.selectedContributionRoleId = roleId;
        document.getElementById("contribution-role").value = roleId;
        renderContributionRoleDetail();
      });
    }
  });

  document.getElementById("contribution-entity-type").addEventListener("change", () => {
    populateContributionEntityOptions();
  });

  document.getElementById("community-post-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitCommunityPost();
  });

  document.getElementById("community-reply-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = document.getElementById("community-reply-body").value.trim();
    if (!body || !state.selectedCommunityPostId) {
      setStatus("community-status", "Choose a thread and add a reply first.", "error");
      return;
    }
    try {
      await fetchJson(`/community/posts/${encodeURIComponent(state.selectedCommunityPostId)}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      document.getElementById("community-reply-body").value = "";
      clearDraft(DRAFT_STORAGE_KEYS.communityReply);
      setStatus("community-status", "Reply added to the selected discussion.", "success");
      await Promise.all([loadCommunityPosts(), loadNotifications()]);
    } catch (error) {
      setStatus("community-status", error.message, "error");
    }
  });

  document.getElementById("community-channel-select").addEventListener("change", async (event) => {
    state.selectedCommunityChannelId = event.target.value;
    state.selectedCommunityPostId = null;
    await loadCommunityPosts();
  });

  document.getElementById("community-moderation-filter").addEventListener("change", async () => {
    state.selectedCommunityPostId = null;
    await loadCommunityPosts();
  });

  document.getElementById("community-related-filter").addEventListener("change", async () => {
    state.selectedCommunityPostId = null;
    await loadCommunityPosts();
  });

  document.getElementById("toggle-advanced-filters").addEventListener("click", () => {
    const container = document.getElementById("advanced-filters");
    const button = document.getElementById("toggle-advanced-filters");
    const isCollapsed = container.classList.toggle("is-collapsed");
    button.textContent = isCollapsed ? "Show advanced filters" : "Hide advanced filters";
  });

  document.querySelectorAll(".export-link").forEach((link) => {
    link.addEventListener("click", () => {
      const format = link.textContent.trim();
      const materialName = link.dataset.materialName || "selected material";
      setStatus("export-studio-status", `Preparing branded ${format} deliverable for ${materialName}.`, "success");
      addActivityEvent("Export prepared", `${format} for ${materialName}`, "export");
    });
  });

}

async function init() {
  loadActiveCase();
  loadUiWorkspaceState();
  loadPersonalWorkspace();
  window.PackGraphChat?.init({
    request: async ({ question, context }) => fetchJson("/query/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        options: { material_id: state.selectedMaterialId, prioritize_sustainability: true },
        context,
      }),
    }),
    onResult: async (question, response) => {
      handleChatResult(question, response);
      await Promise.all([loadReviewQueue(), loadNotifications(), loadOperationsDashboard()]);
    },
  });
  setupThemeToggle();
  setupShellNavigation();
  setupPageNavigation();
  setupNavigation();
  setupGraphZoomControls();
  setupGraphPanControls();
  setupGraphFilters();
  setupForms();
  setupDraftPersistence();
  setupOverviewOnboardingHint();
  setNotificationFilter("all");
  renderCaseWorkspace();
  renderWorkflowMap();
  renderPersonalWorkspace();
  renderActivityTimeline();
  await loadPrivateDataStatus();
  await loadSession();
  await Promise.all([
    loadMaterials(),
    loadCompliance(),
    loadAlerts(),
    loadInvestigations(),
    loadWorkspaces(),
    loadProjectMemory(),
    loadSourceIntakeSources(),
    loadReviewQueue(),
    loadSavedSearches(),
    loadNotifications(),
    loadOperationsDashboard(),
    loadScenarioHistory(),
    loadRecommendationsSummary(),
    loadAnalytics(),
    loadBenchmarks(),
    loadTrendCharts(),
    loadContributionData(),
    loadCommunityData(),
  ]);
  await runComparison();
  renderCompareSelectionSummary();
  await runScenario();
  await loadGraphPath();
  await loadMaterialTimeline();
  await loadExploreEntities();
  updatePageContextCard();
  renderStructuredAnswer({
    title: "Decision output",
    summary: "Run a natural-language question to see structured recommendations, reasons, risk flags, and next steps.",
    recommendations: [],
    reasons: [],
    risk_flags: [],
    next_steps: [],
  });
  renderQueryRows([]);
  renderExecutionDebug({});
  renderSupplierDetail(null);
  renderRegulationDetail(null);
  if (window.PackGraphExplorePage) {
    window.PackGraphExplorePage.renderDetail(null, jumpExploreToDashboard);
  }
  if (window.PackGraphCommunityPage) {
    window.PackGraphCommunityPage.renderDetail(null);
  }
  renderCrossPageContext();
  renderRoleDashboard();
  addMessage("PackGraph", "Start in Overview, move to Workbench for deeper evaluation, and use Intelligence for graph, analytics, alerts, and benchmark context.");
  const requestedSection = new URLSearchParams(window.location.search).get("section");
  const requestedPage = new URLSearchParams(window.location.search).get("page");
  if (["dashboard", "explore", "contribute", "community"].includes(requestedSection) && requestedSection !== "dashboard") {
    setSection(requestedSection);
  }
  if (["overview", "workbench", "intelligence"].includes(requestedPage)) {
    setPage(requestedPage);
  }
  if (window.PackGraphUI?.initGuidedTour) {
    window.PackGraphUI.initGuidedTour({
      navigator: async (step) => {
        if (step.section && step.section !== "dashboard") {
          setSection(step.section);
        } else if (step.section === "dashboard") {
          setSection("dashboard");
        }
        if (step.page) {
          setPage(step.page);
        }
      },
      steps: [
        { section: "dashboard", page: "overview", selector: "#chat-panel", title: "Chat", body: "Start here to ask natural-language questions and get the main decision answer." },
        { section: "explore", selector: ".explore-shell-panel", title: "Explore", body: "Browse materials, products, and updates before you move into a decision workflow." },
        { section: "dashboard", page: "workbench", selector: ".workbench-primary-panel", title: "Projects", body: "Use this workspace to compare shortlisted options, test scenarios, and package exports." },
        { section: "contribute", selector: ".contribute-shell", title: "Contribute", body: "Add new findings, evidence, and corrections through structured contribution flows." },
        { section: "community", selector: ".community-shell", title: "Community", body: "Discuss sourcing, materials, and regulations without losing context from the product graph." },
        { section: "dashboard", page: "workbench", selector: "#provenance-panel", title: "Review", body: "Review evidence, extracted fields, and missing proof before you trust a recommendation." },
        { section: "dashboard", page: "intelligence", selector: "#graph-subgraph", title: "Resolution", body: "Use graph context and node relationships to resolve duplicates, ambiguity, and final decision context." },
      ],
    });
  }
}

init();
