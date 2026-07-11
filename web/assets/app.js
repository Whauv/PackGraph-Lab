const state = {
  materials: [],
  selectedMaterialId: null,
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  return payload.data;
}

function formatTags(items) {
  return `<div class="tags">${items.map((item) => `<span class="tag">${item}</span>`).join("")}</div>`;
}

function addMessage(author, text, detail = "") {
  const log = document.getElementById("chat-log");
  const message = document.createElement("div");
  message.className = "message";
  message.innerHTML = `<strong>${author}</strong><div>${text}</div>${detail ? `<pre>${detail}</pre>` : ""}`;
  log.prepend(message);
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
  select.innerHTML = state.materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("");
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
  document.getElementById("material-detail").innerHTML = `
    <div class="detail-card"><strong>Composition</strong><p>${material.composition}</p>${formatTags(material.regions_available)}</div>
    <div class="detail-card"><strong>Performance</strong><p>O2 barrier ${material.oxygen_barrier} / Moisture ${material.moisture_barrier} / Seal ${material.seal_strength}</p>${formatTags(material.compliance_flags.length ? material.compliance_flags : ["compliant profile"])}</div>
    <div class="detail-card"><strong>Economics</strong><p>${material.cost_range.low} to ${material.cost_range.high} ${material.cost_range.currency}</p><p>Sustainability ${material.sustainability_score} / Recyclability ${material.recyclability_score}</p></div>
  `;
}

async function loadSuppliers() {
  const suppliers = await fetchJson("/suppliers");
  document.getElementById("supplier-table").innerHTML = `
    <table>
      <thead><tr><th>Supplier</th><th>Country</th><th>ESG</th><th>Risk</th><th>Lead time</th></tr></thead>
      <tbody>
        ${suppliers.slice(0, 12).map((item) => `<tr><td>${item.name}</td><td>${item.country}</td><td>${item.esg_score}</td><td>${item.disruption_risk_score}</td><td>${item.lead_time_days} days</td></tr>`).join("")}
      </tbody>
    </table>
  `;
}

async function loadProvenance() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("provenance-panel").innerHTML = `
    <div class="detail-card"><strong>Documents</strong>${material.documents.map((doc) => `<p>${doc.title}<br/><small>${doc.document_type} · score ${doc.provenance_score}</small></p>`).join("")}</div>
    <div class="detail-card"><strong>Test reports</strong>${material.test_reports.map((report) => `<p>${report.title}<br/><small>${report.lab} · migration ${report.migration_status}</small></p>`).join("")}</div>
  `;
}

async function loadCompliance() {
  const dashboard = await fetchJson("/compliance/dashboard");
  document.getElementById("compliance-summary").innerHTML = `
    <div class="metric"><div class="value">${dashboard.watch_count}</div><div>watch-list materials</div></div>
    <div class="metric"><div class="value">${dashboard.non_compliant_count}</div><div>non-compliant materials</div></div>
  `;
  document.getElementById("regulation-list").innerHTML = dashboard.upcoming_regulations.map((item) => `<span class="pill">${item.name}</span>`).join("");
}

async function loadInvestigations() {
  const investigations = await fetchJson("/investigations");
  document.getElementById("investigation-count").textContent = `${investigations.length} active`;
  document.getElementById("investigation-list").innerHTML = investigations.map((item) => `
    <div class="row-card">
      <strong>${item.title}</strong>
      <p>${item.notes}</p>
      <p>${item.decision_rationale}</p>
    </div>
  `).join("");
}

async function loadRelationships() {
  const links = await fetchJson(`/graph/relationships?material_id=${state.selectedMaterialId}`);
  document.getElementById("relationship-list").innerHTML = links.slice(0, 14).map((item) => `
    <div class="row-card"><span>${item.from}</span><strong>${item.type}</strong><span>${item.to}</span></div>
  `).join("");
}

async function loadTimeline() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("timeline-list").innerHTML = material.snapshots.slice(0, 10).map((item) => `
    <div class="row-card">
      <strong>${item.quarter}</strong>
      <p>Cost ${item.price_usd_per_kg} USD/kg · Lead ${item.lead_time_days} days</p>
      <p>Compliance ${item.compliance_state} · Risk ${item.risk_score}</p>
    </div>
  `).join("");
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
  document.querySelectorAll("[data-tab-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`.tab[data-tab="${button.dataset.tabTarget}"]`)?.click();
    });
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
  setupTabs();
  setupForms();
  await Promise.all([loadRuntime(), loadMaterials(), loadSuppliers(), loadCompliance(), loadInvestigations()]);
  await Promise.all([loadProvenance(), loadTimeline(), loadRelationships()]);
  addMessage("PackGraph", "Ready with synthetic packaging data, reviewed query routing, and scenario simulation.");
}

init();
