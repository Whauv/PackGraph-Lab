const state = {
  materials: [],
  selectedMaterialId: null,
  theme: "light",
};

function applyTheme(theme) {
  state.theme = theme;
  document.body.setAttribute("data-theme", theme);
  const button = document.getElementById("theme-toggle");
  if (button) {
    button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  }
  window.localStorage.setItem("packgraph-theme", theme);
}

function setupThemeToggle() {
  const savedTheme = window.localStorage.getItem("packgraph-theme");
  const preferredDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(savedTheme || (preferredDark ? "dark" : "light"));
  document.getElementById("theme-toggle").addEventListener("click", () => {
    applyTheme(state.theme === "dark" ? "light" : "dark");
  });
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
  return value
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

async function loadRuntime() {
  const backends = await fetchJson("/runtime/backends");
  const active = backends.find((item) => item.active) || backends[0];
  document.getElementById("active-backend").textContent = `${active.backend} / ${active.mode}`;
}

async function loadMaterials() {
  const payload = await fetch("/materials");
  const body = await payload.json();
  state.materials = body.data;
  state.selectedMaterialId = state.materials[0]?.material_id;
  document.getElementById("dataset-scale").textContent = `${body.meta.materials} materials / ${body.meta.relationships} links`;

  const select = document.getElementById("material-select");
  select.innerHTML = state.materials
    .map((item) => `<option value="${item.material_id}">${item.name}</option>`)
    .join("");
  select.value = state.selectedMaterialId;
  select.addEventListener("change", async (event) => {
    state.selectedMaterialId = event.target.value;
    await Promise.all([loadMaterialDetail(), loadProvenance(), loadTimeline(), loadRelationships()]);
  });

  await loadMaterialDetail();
}

async function loadMaterialDetail() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("material-title").textContent = `${material.name} (${material.category})`;

  const supplierNames = material.suppliers.map((item) => item.name);
  const substitutes = material.substitute_material_ids
    .map((id) => state.materials.find((materialItem) => materialItem.material_id === id)?.name || id);

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
    </div>
  `;
}

async function loadSuppliers() {
  const suppliers = await fetchJson("/suppliers");
  document.getElementById("supplier-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Supplier</th>
          <th>Country</th>
          <th>ESG</th>
          <th>Risk</th>
          <th>Lead time</th>
        </tr>
      </thead>
      <tbody>
        ${suppliers
          .slice(0, 12)
          .map(
            (item) => `
              <tr>
                <td>${item.name}</td>
                <td>${item.country}</td>
                <td>${item.esg_score}</td>
                <td><span class="${riskClass(item.disruption_risk_score)}">${item.disruption_risk_score}</span></td>
                <td>${item.lead_time_days} days</td>
              </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function loadProvenance() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("provenance-panel").innerHTML = `
    <div class="detail-card">
      <h4>Documents</h4>
      ${material.documents
        .map(
          (doc) => `
            <div class="row-card">
              <strong>${doc.title}</strong>
              <p>${doc.document_type}</p>
              <small>Provenance score ${doc.provenance_score} / issued ${doc.issued_on}</small>
            </div>`
        )
        .join("")}
    </div>
    <div class="detail-card">
      <h4>Test reports</h4>
      ${material.test_reports
        .map(
          (report) => `
            <div class="row-card">
              <strong>${report.title}</strong>
              <p>${report.lab}</p>
              <small>Migration ${report.migration_status} / test date ${report.test_date}</small>
            </div>`
        )
        .join("")}
    </div>
  `;
}

async function loadCompliance() {
  const dashboard = await fetchJson("/compliance/dashboard");
  document.getElementById("compliance-summary").innerHTML = `
    <div class="metric">
      <div class="value">${dashboard.watch_count}</div>
      <div>materials under review</div>
    </div>
    <div class="metric">
      <div class="value">${dashboard.non_compliant_count}</div>
      <div>materials out of bounds</div>
    </div>
  `;
  document.getElementById("regulation-list").innerHTML = dashboard.upcoming_regulations
    .map((item) => `<span class="pill">${item.name}</span>`)
    .join("");
  document.getElementById("compliance-risk-list").innerHTML = dashboard.at_risk_materials
    .slice(0, 5)
    .map(
      (item) => `
        <div class="row-card">
          <strong>${item.name}</strong>
          <p>Average supplier risk ${item.supplier_risk_score}</p>
        </div>`
    )
    .join("");
  document.getElementById("hero-risk-count").textContent = dashboard.at_risk_materials.length;
  document.getElementById("hero-regulations").textContent = dashboard.upcoming_regulations.length;
}

async function loadInvestigations() {
  const investigations = await fetchJson("/investigations");
  document.getElementById("investigation-count").textContent = `${investigations.length} active`;
  document.getElementById("investigation-list").innerHTML = investigations
    .map(
      (item) => `
        <div class="row-card">
          <strong>${item.title}</strong>
          <p>${item.notes}</p>
          <small>${item.decision_rationale}</small>
        </div>`
    )
    .join("");
}

async function loadRelationships() {
  const links = await fetchJson(`/graph/relationships?material_id=${state.selectedMaterialId}`);
  document.getElementById("relationship-list").innerHTML = links
    .slice(0, 14)
    .map(
      (item) => `
        <div class="row-card relationship-row">
          <span>${item.from}</span>
          <strong>${titleCase(item.type)}</strong>
          <span>${item.to}</span>
        </div>`
    )
    .join("");
}

async function loadTimeline() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("timeline-list").innerHTML = material.snapshots
    .slice(0, 10)
    .map(
      (item) => `
        <div class="row-card">
          <strong>${item.quarter}</strong>
          <p>Cost ${item.price_usd_per_kg} USD/kg / Lead ${item.lead_time_days} days</p>
          <p>Compliance ${titleCase(item.compliance_state)} / Risk ${item.risk_score}</p>
        </div>`
    )
    .join("");
}

async function loadRecommendationsSummary() {
  const recommendations = await fetchJson("/query/recommendations?prioritize_sustainability=true");
  document.getElementById("hero-recommendations").textContent = recommendations.length;
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
  document.getElementById("jump-chat").addEventListener("click", () => {
    document.getElementById("chat-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  });
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
      body: JSON.stringify({
        question,
        options: { material_id: state.selectedMaterialId, prioritize_sustainability: true },
      }),
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
        shortlisted_material_ids: [state.selectedMaterialId],
        comparison_material_ids: [state.selectedMaterialId],
        decision_rationale: "Saved from the PackGraph Lab workspace.",
      }),
    });
    document.getElementById("investigation-title").value = "";
    document.getElementById("investigation-notes").value = "";
    await loadInvestigations();
  });

  document.getElementById("scenario-button").addEventListener("click", async () => {
    const scenario = await fetchJson("/query/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        material_id: state.selectedMaterialId,
        scenario: "what if compostability becomes the top priority",
      }),
    });
    addMessage("Scenario", scenario.summary, JSON.stringify(scenario.actions, null, 2));
  });
}

async function init() {
  setupThemeToggle();
  setupTabs();
  setupNavigation();
  setupForms();
  await Promise.all([
    loadRuntime(),
    loadMaterials(),
    loadSuppliers(),
    loadCompliance(),
    loadInvestigations(),
    loadRecommendationsSummary(),
  ]);
  await Promise.all([loadProvenance(), loadTimeline(), loadRelationships()]);
  addMessage("PackGraph", "Ready with synthetic packaging data, reviewed query routing, and scenario simulation.");
}

init();
