const state = {
  materials: [],
  filteredMaterials: [],
  selectedMaterialId: null,
  theme: "light",
  currentUser: null,
};

function applyTheme(theme) {
  state.theme = theme;
  document.body.setAttribute("data-theme", theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  window.localStorage.setItem("packgraph-theme", theme);
}

function setupThemeToggle() {
  const savedTheme = window.localStorage.getItem("packgraph-theme");
  const preferredDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(savedTheme || (preferredDark ? "dark" : "light"));
  document.getElementById("theme-toggle").addEventListener("click", () => applyTheme(state.theme === "dark" ? "light" : "dark"));
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  return payload.data;
}

function formatTags(items, className = "tag") {
  return `<div class="tags">${items.map((item) => `<span class="${className}">${item}</span>`).join("")}</div>`;
}

function addMessage(author, text, detail = "") {
  const log = document.getElementById("chat-log");
  const message = document.createElement("div");
  message.className = "message";
  message.innerHTML = `<strong>${author}</strong><div>${text}</div>${detail ? `<pre>${detail}</pre>` : ""}`;
  log.prepend(message);
}

function titleCase(value) {
  return String(value)
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((item) => item.charAt(0).toUpperCase() + item.slice(1))
    .join(" ");
}

function riskClass(score) {
  if (score >= 68) return "risk-high";
  if (score >= 50) return "risk-medium";
  return "risk-low";
}

function selectedMaterialsFromCompare() {
  return Array.from(document.getElementById("compare-materials").selectedOptions).map((option) => option.value);
}

function currentMaterialPool() {
  return state.filteredMaterials.length ? state.filteredMaterials : state.materials;
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
}

async function loadSession() {
  state.currentUser = await fetchJson("/auth/session");
  const card = document.getElementById("user-card");
  if (!state.currentUser) {
    card.innerHTML = "<span>No active user</span>";
    return;
  }
  card.innerHTML = `<span>${state.currentUser.role}</span><strong>${state.currentUser.name}</strong><small>${state.currentUser.email}</small>`;
}

async function loadRuntime() {
  const backends = await fetchJson("/runtime/backends");
  const active = backends.find((item) => item.active) || backends[0];
  document.getElementById("active-backend").textContent = `${active.backend} / ${active.mode}`;
}

async function loadMaterials() {
  const payload = await fetch("/materials");
  const body = await payload.json();
  state.materials = body.data;
  state.filteredMaterials = [...state.materials];
  state.selectedMaterialId = state.materials[0]?.material_id;
  document.getElementById("dataset-scale").textContent = `${body.meta.materials} materials / ${body.meta.relationships} links`;
  populateMaterialControls(state.materials);
  populateFilterOptions();
  document.getElementById("material-select").addEventListener("change", async (event) => {
    state.selectedMaterialId = event.target.value;
    await refreshMaterialContext();
  });
  await refreshMaterialContext();
}

function populateFilterOptions() {
  const regions = [...new Set(state.materials.flatMap((item) => item.regions_available))].sort();
  const categories = [...new Set(state.materials.map((item) => item.category))].sort();
  document.getElementById("filter-region").innerHTML = `<option value="">All regions</option>${regions.map((item) => `<option value="${item}">${item}</option>`).join("")}`;
  document.getElementById("filter-category").innerHTML = `<option value="">All categories</option>${categories.map((item) => `<option value="${item}">${titleCase(item)}</option>`).join("")}`;
}

async function refreshMaterialContext() {
  await Promise.all([loadMaterialDetail(), loadProvenance(), loadGraph(), loadTimeline()]);
}

async function loadMaterialDetail() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("material-title").textContent = `${material.name} (${material.category})`;
  const supplierNames = material.suppliers.map((item) => item.name);
  const substitutes = material.substitute_material_ids.map((id) => state.materials.find((entry) => entry.material_id === id)?.name || id);
  document.getElementById("material-detail").innerHTML = `
    <div class="detail-primary">
      <div class="detail-card">
        <h5>Profile</h5>
        <h4>Material profile</h4>
        <p>${material.composition}</p>
        ${formatTags(material.regions_available)}
        <div class="key-facts">
          <div class="fact"><span>Descriptor</span><strong>${titleCase(material.descriptor)}</strong></div>
          <div class="fact"><span>Food contact</span><strong>${material.food_contact_safe ? "Approved profile" : "Review required"}</strong></div>
          <div class="fact"><span>Applications</span><strong>${material.target_applications.length} active targets</strong></div>
          <div class="fact"><span>Suppliers</span><strong>${material.supplier_ids.length} qualified sources</strong></div>
        </div>
      </div>
      <div class="detail-card">
        <h5>Measured performance</h5>
        <h4>Performance and economics</h4>
        <div class="score-grid">
          <div class="detail-card">
            <div class="score-row"><span>Oxygen barrier</span><strong>${material.oxygen_barrier}</strong></div>
            <div class="score-row"><span>Moisture barrier</span><strong>${material.moisture_barrier}</strong></div>
            <div class="score-row"><span>Seal strength</span><strong>${material.seal_strength}</strong></div>
            <div class="score-row"><span>Thermal tolerance</span><strong>${material.thermal_tolerance}</strong></div>
          </div>
          <div class="detail-card">
            <div class="score-row"><span>Recyclability</span><strong>${material.recyclability_score}</strong></div>
            <div class="score-row"><span>Compostability</span><strong>${material.compostability_score}</strong></div>
            <div class="score-row"><span>Sustainability</span><strong>${material.sustainability_score}</strong></div>
            <div class="score-row"><span>Cost range</span><strong>${material.cost_range.low} to ${material.cost_range.high} ${material.cost_range.currency}</strong></div>
          </div>
        </div>
      </div>
    </div>
    <div class="detail-secondary">
      <div class="detail-card">
        <h5>Compliance view</h5>
        <h4>Compliance and substitutes</h4>
        <p>Current state: <strong>${titleCase(material.compliance_state)}</strong></p>
        ${formatTags((material.compliance_flags.length ? material.compliance_flags : ["compliant profile"]).map(titleCase))}
        <div class="subsection">
          <div class="subsection-heading">Substitute materials</div>
          ${formatTags(substitutes)}
        </div>
      </div>
      <div class="detail-card">
        <h5>Qualified supply</h5>
        <h4>Qualified suppliers</h4>
        ${supplierNames.map((name) => `<div class="score-row"><span>${name}</span><strong>Available</strong></div>`).join("")}
      </div>
    </div>`;
}

async function loadProvenance(searchQuery = "") {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("provenance-panel").innerHTML = `
    <div class="detail-card">
      <h4>Documents</h4>
      ${material.documents.map((doc) => `<div class="row-card"><strong>${doc.title}</strong><p>${doc.document_type}</p><small>Provenance score ${doc.provenance_score} / issued ${doc.issued_on}</small></div>`).join("")}
    </div>
    <div class="detail-card">
      <h4>Test reports</h4>
      ${material.test_reports.map((report) => `<div class="row-card"><strong>${report.title}</strong><p>${report.lab}</p><small>Migration ${report.migration_status} / test date ${report.test_date}</small></div>`).join("")}
    </div>`;
  if (searchQuery) {
    const results = await fetchJson(`/documents/search?query=${encodeURIComponent(searchQuery)}&material_id=${state.selectedMaterialId}`);
    document.getElementById("document-search-results").innerHTML = results.map((item) => `<div class="row-card"><strong>${item.title || item.report_id}</strong><p>${titleCase(item.type)} / ${item.document_type || item.lab || ""}</p></div>`).join("");
  } else {
    document.getElementById("document-search-results").innerHTML = "";
  }
}

async function loadCompliance() {
  const dashboard = await fetchJson("/compliance/dashboard");
  document.getElementById("compliance-summary").innerHTML = `
    <div class="metric"><div class="value">${dashboard.watch_count}</div><div>materials under review</div></div>
    <div class="metric"><div class="value">${dashboard.non_compliant_count}</div><div>materials out of bounds</div></div>`;
  document.getElementById("regulation-list").innerHTML = dashboard.upcoming_regulations.map((item) => `<span class="pill">${item.name}</span>`).join("");
  document.getElementById("compliance-risk-list").innerHTML = dashboard.at_risk_materials.slice(0, 5).map((item) => `<div class="row-card"><strong>${item.name}</strong><p>Average supplier risk ${item.supplier_risk_score}</p></div>`).join("");
  document.getElementById("hero-risk-count").textContent = dashboard.at_risk_materials.length;
  document.getElementById("hero-regulations").textContent = dashboard.upcoming_regulations.length;
}

async function loadAlerts() {
  const alerts = await fetchJson("/alerts");
  document.getElementById("hero-alert-count").textContent = alerts.length;
  document.getElementById("alerts-list").innerHTML = alerts.map((item) => `<div class="row-card"><strong>${item.title}</strong><p>${item.detail}</p><small>${titleCase(item.severity)} / ${titleCase(item.category)}</small></div>`).join("");
}

async function loadInvestigations() {
  const investigations = await fetchJson("/investigations");
  document.getElementById("investigation-count").textContent = `${investigations.length} active`;
  document.getElementById("investigation-list").innerHTML = investigations.map((item) => `
    <div class="row-card">
      <strong>${item.title}</strong>
      <p>${item.notes}</p>
      <small>${item.decision_rationale}</small>
      <div class="row-actions">
        <a class="mini-action link-action" href="/investigations/${item.investigation_id}/export.csv" target="_blank">CSV</a>
        <a class="mini-action link-action" href="/investigations/${item.investigation_id}/export.pdf" target="_blank">PDF</a>
      </div>
    </div>`).join("");
}

async function loadWorkspaces() {
  const workspaces = await fetchJson("/workspaces");
  document.getElementById("workspace-list").innerHTML = workspaces.map((item) => `<div class="row-card"><strong>${item.name}</strong><p>${item.selected_material_ids.length} materials / tab ${titleCase(item.active_tab)}</p></div>`).join("");
}

async function loadGraph() {
  const graph = await fetchJson(`/graph/subgraph?material_id=${state.selectedMaterialId}`);
  document.getElementById("graph-subgraph").innerHTML = graph.nodes.map((node) => `<button type="button" class="graph-node" data-node-id="${node.id}"><span>${titleCase(node.type)}</span><strong>${node.label}</strong></button>`).join("");
  const selectors = [document.getElementById("graph-source"), document.getElementById("graph-target")];
  selectors.forEach((select) => {
    select.innerHTML = graph.nodes.map((node) => `<option value="${node.id}">${node.label}</option>`).join("");
  });
  document.getElementById("graph-source").value = state.selectedMaterialId;
  document.getElementById("graph-target").value = graph.nodes.find((node) => node.id !== state.selectedMaterialId)?.id || state.selectedMaterialId;
  document.querySelectorAll(".graph-node").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById("graph-source").value = button.dataset.nodeId;
    });
  });
  const links = await fetchJson(`/graph/relationships?material_id=${state.selectedMaterialId}`);
  document.getElementById("relationship-list").innerHTML = links.slice(0, 14).map((item) => `<div class="row-card relationship-row"><span>${item.from}</span><strong>${titleCase(item.type)}</strong><span>${item.to}</span></div>`).join("");
}

async function loadGraphPath() {
  const sourceId = document.getElementById("graph-source").value;
  const targetId = document.getElementById("graph-target").value;
  const result = await fetchJson(`/graph/path?source_id=${sourceId}&target_id=${targetId}`);
  document.getElementById("graph-path-results").innerHTML = result.path.length
    ? result.path.map((node, index) => `<div class="row-card"><strong>${index + 1}. ${node.label}</strong><p>${titleCase(node.type)}</p></div>`).join("")
    : `<div class="row-card"><strong>No path found</strong><p>Try another source or target node.</p></div>`;
}

async function loadTimeline() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("timeline-list")?.remove;
  const existing = document.getElementById("timeline-list");
  if (existing) {
    existing.innerHTML = material.snapshots.slice(0, 10).map((item) => `<div class="row-card"><strong>${item.quarter}</strong><p>Cost ${item.price_usd_per_kg} USD/kg / Lead ${item.lead_time_days} days</p><p>Compliance ${titleCase(item.compliance_state)} / Risk ${item.risk_score}</p></div>`).join("");
  }
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
  document.getElementById("compare-results").innerHTML = results.map((item) => `<div class="row-card"><strong>${item.name}</strong><p>Weighted score ${item.weighted_score}</p><small>Sustainability ${item.scores.sustainability} / Recyclability ${item.scores.recyclability} / Cost efficiency ${item.scores.cost_efficiency}</small></div>`).join("");
}

async function loadAnalytics() {
  const data = await fetchJson("/analytics/overview");
  const latestCost = data.cost_trends[data.cost_trends.length - 1];
  const latestCompliance = data.compliance_drift[data.compliance_drift.length - 1];
  document.getElementById("analytics-summary").innerHTML = `
    <div class="metric"><div class="value">${latestCost.average_price_usd_per_kg}</div><div>latest avg price / kg</div></div>
    <div class="metric"><div class="value">${latestCost.average_lead_time_days}</div><div>latest avg lead time</div></div>
    <div class="metric"><div class="value">${latestCompliance.watch_count}</div><div>watch states in latest quarter</div></div>
    <div class="metric"><div class="value">${latestCompliance.non_compliant_count}</div><div>non-compliant states in latest quarter</div></div>`;
  document.getElementById("cost-trends").innerHTML = data.cost_trends.map((item) => `<div class="row-card"><strong>${item.quarter}</strong><p>${item.average_price_usd_per_kg} USD/kg average price</p><small>${item.average_lead_time_days} day lead-time average</small></div>`).join("");
  document.getElementById("compliance-drift").innerHTML = data.compliance_drift.map((item) => `<div class="row-card"><strong>${item.quarter}</strong><p>${item.watch_count} watch / ${item.non_compliant_count} non-compliant</p></div>`).join("");
  document.getElementById("supplier-performance").innerHTML = `
    <table>
      <thead><tr><th>Supplier</th><th>ESG</th><th>Risk</th><th>Lead time</th><th>Compliance</th></tr></thead>
      <tbody>
      ${data.supplier_performance.map((item) => `<tr><td>${item.name}</td><td>${item.esg_score}</td><td><span class="${riskClass(item.disruption_risk_score)}">${item.disruption_risk_score}</span></td><td>${item.lead_time_days}</td><td>${item.average_compliance_rate ?? "-"}</td></tr>`).join("")}
      </tbody>
    </table>`;
}

async function loadBenchmarks() {
  const data = await fetchJson("/benchmarks");
  const neo4jStatus = data.neo4j?.status || data.status || "not-run";
  const memgraphStatus = data.memgraph?.status || "not-run";
  document.getElementById("benchmark-status").innerHTML = `
    <div class="metric"><div class="value">${titleCase(neo4jStatus)}</div><div>Neo4j benchmark state</div></div>
    <div class="metric"><div class="value">${titleCase(memgraphStatus)}</div><div>Memgraph benchmark state</div></div>`;
  document.getElementById("benchmark-query-set").innerHTML = (data.query_set || []).map((item) => `<div class="row-card"><strong>${item.query}</strong><p>${item.note}</p></div>`).join("");
  document.getElementById("benchmark-plan-notes").innerHTML = (data.query_plan_notes || data.notes || []).map((item) => `<div class="row-card"><p>${item.note || item}</p></div>`).join("");
}

async function applyFilters() {
  const search = document.getElementById("filter-search").value.trim();
  const region = document.getElementById("filter-region").value;
  const category = document.getElementById("filter-category").value;
  const compliance = document.getElementById("filter-compliance").value;
  const sustainability = document.getElementById("filter-sustainability").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (region) params.set("region", region);
  if (category) params.set("category", category);
  if (compliance) params.set("compliance_state", compliance);
  if (sustainability) params.set("min_sustainability", sustainability);
  const results = await fetchJson(`/materials/filter?${params.toString()}`);
  state.filteredMaterials = results;
  populateMaterialControls(results.length ? results : state.materials);
  document.getElementById("filter-results-summary").textContent = results.length ? `Showing ${results.length} filtered materials` : "No materials matched. Reverting to full portfolio.";
  if (!results.length) state.filteredMaterials = [];
  await refreshMaterialContext();
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      document.querySelector(`[data-panel="${button.dataset.tab}"]`).classList.add("active");
    });
  });
}

function setupNavigation() {
  document.getElementById("jump-chat").addEventListener("click", () => document.getElementById("chat-panel").scrollIntoView({ behavior: "smooth", block: "start" }));
  document.getElementById("jump-workspace").addEventListener("click", () => {
    document.querySelector(`.tab[data-tab="workspace"]`)?.click();
    document.querySelector(`[data-panel="workspace"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function setupForms() {
  document.getElementById("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = document.getElementById("question-input").value.trim();
    if (!question) return;
    const response = await fetchJson("/query/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, options: { material_id: state.selectedMaterialId, prioritize_sustainability: true } }),
    });
    addMessage("Question", question);
    addMessage("PackGraph", response.message, JSON.stringify(response.plan.audit, null, 2));
  });

  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      document.getElementById("question-input").value = button.dataset.prompt;
      document.getElementById("ask-form").requestSubmit();
    });
  });

  document.getElementById("investigation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = document.getElementById("investigation-title").value.trim();
    const notes = document.getElementById("investigation-notes").value.trim();
    if (!title) return;
    await fetchJson("/investigations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        notes,
        focus_material_id: state.selectedMaterialId,
        shortlisted_material_ids: selectedMaterialsFromCompare().length ? selectedMaterialsFromCompare() : [state.selectedMaterialId],
        comparison_material_ids: selectedMaterialsFromCompare().length ? selectedMaterialsFromCompare() : [state.selectedMaterialId],
        decision_rationale: "Saved from the PackGraph Lab workspace with current comparison and filter context.",
      }),
    });
    document.getElementById("investigation-title").value = "";
    document.getElementById("investigation-notes").value = "";
    await loadInvestigations();
  });

  document.getElementById("scenario-button")?.addEventListener("click", async () => {
    const scenario = await fetchJson("/query/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ material_id: state.selectedMaterialId, scenario: "what if compostability becomes the top priority" }),
    });
    addMessage("Scenario", scenario.summary, JSON.stringify(scenario.actions, null, 2));
  });

  document.getElementById("filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await applyFilters();
  });

  document.getElementById("compare-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runComparison();
  });

  document.getElementById("document-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("document-search-input").value.trim();
    await loadProvenance(query);
  });

  document.getElementById("graph-path-button").addEventListener("click", async () => {
    await loadGraphPath();
  });

  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await fetchJson("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("login-email").value.trim(),
        password: document.getElementById("login-password").value,
      }),
    });
    await Promise.all([loadSession(), loadInvestigations(), loadWorkspaces()]);
  });

  document.getElementById("workspace-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("workspace-name").value.trim();
    if (!name) return;
    await fetchJson("/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        filters: {
          search: document.getElementById("filter-search").value.trim(),
          region: document.getElementById("filter-region").value,
          category: document.getElementById("filter-category").value,
          compliance_state: document.getElementById("filter-compliance").value,
          min_sustainability: document.getElementById("filter-sustainability").value,
        },
        selected_material_ids: selectedMaterialsFromCompare().length ? selectedMaterialsFromCompare() : [state.selectedMaterialId],
        active_tab: document.querySelector(".tab.active")?.dataset.tab || "materials",
      }),
    });
    document.getElementById("workspace-name").value = "";
    await loadWorkspaces();
  });
}

async function init() {
  setupThemeToggle();
  setupTabs();
  setupNavigation();
  setupForms();
  await Promise.all([loadSession(), loadRuntime(), loadMaterials(), loadCompliance(), loadAlerts(), loadInvestigations(), loadWorkspaces(), loadRecommendationsSummary(), loadAnalytics(), loadBenchmarks()]);
  await runComparison();
  await loadGraphPath();
  addMessage("PackGraph", "Ready with graph exploration, filtering, comparison, document search, alerts, exports, analytics, and benchmark coverage.");
}

init();
