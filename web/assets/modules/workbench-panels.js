window.PackGraphWorkbenchPanels = {
  renderComparisonMatrix(results) {
    const container = document.getElementById("comparison-matrix");
    if (!container) return;
    if (!results || !results.length) {
      container.innerHTML = "<table><tbody><tr><td>No shortlisted materials selected yet.</td></tr></tbody></table>";
      return;
    }
    const metrics = [
      ["Material", (item) => item.name],
      ["Category", (item) => item.category],
      ["Descriptor", (item) => item.descriptor],
      ["Weighted score", (item) => item.weighted_score],
      ["Compliance", (item) => item.compliance_state],
      ["Suppliers", (item) => item.supplier_count],
      ["High cost", (item) => `${item.cost_range.high} ${item.cost_range.currency}`],
      ["Sustainability", (item) => item.scores.sustainability],
      ["Recyclability", (item) => item.scores.recyclability],
      ["Compostability", (item) => item.scores.compostability],
      ["Oxygen barrier", (item) => item.scores.oxygen_barrier],
      ["Moisture barrier", (item) => item.scores.moisture_barrier],
    ];
    container.innerHTML = `
      <table class="comparison-matrix-table">
        <thead>
          <tr>
            <th>Metric</th>
            ${results.map((item) => `<th>${this.escape(item.name)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${metrics.map(([label, getter]) => `
            <tr>
              <td>${this.escape(label)}</td>
              ${results.map((item) => `<td>${this.escape(getter(item))}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>`;
  },

  renderEvidenceExtraction(items) {
    const container = document.getElementById("evidence-extraction-panel");
    if (!container) return;
    const normalized = (items || []).filter((item) => item.extraction_summary || item.extraction_confidence || item.missing_fields);
    container.innerHTML = normalized.length
      ? normalized.slice(0, 8).map((item) => `
        <div class="row-card">
          <strong>${this.escape(item.title || item.report_id || item.document_id || "Evidence")}</strong>
          <p>${this.escape(item.extraction_summary || "No extraction summary available.")}</p>
          <small>Confidence ${this.escape(Math.round((item.extraction_confidence || 0) * 100))}%</small>
          ${(item.missing_fields || []).length ? `<div class="tags">${item.missing_fields.map((field) => `<span class="tag">Missing ${this.escape(field)}</span>`).join("")}</div>` : ""}
        </div>`).join("")
      : `<div class="row-card"><p>Upload or search evidence to see extracted fields and missing-data flags.</p></div>`;
  },

  renderInvestigations(investigations, onResume) {
    const container = document.getElementById("investigation-list");
    if (!container) return;
    container.innerHTML = investigations.length
      ? investigations.map((item) => `
        <div class="row-card">
          <strong>${this.escape(item.title)}</strong>
          <p>${this.escape(item.notes || "No notes captured yet.")}</p>
          <small>Shortlist ${this.escape((item.shortlisted_material_ids || []).length)} | Status ${this.escape(item.status || "open")}</small>
          <div class="row-actions">
            <button type="button" class="mini-action" data-resume-investigation="${item.investigation_id}">Resume</button>
            <a class="mini-action link-action" href="/investigations/${item.investigation_id}/export.csv" target="_blank">CSV</a>
            <a class="mini-action link-action" href="/investigations/${item.investigation_id}/export.pdf" target="_blank">PDF</a>
          </div>
        </div>`).join("")
      : `<div class="row-card"><p>No investigations saved yet.</p></div>`;
    container.querySelectorAll("[data-resume-investigation]").forEach((button) => {
      button.addEventListener("click", () => onResume(button.dataset.resumeInvestigation));
    });
  },

  renderWorkspaces(workspaces, onResume) {
    const container = document.getElementById("workspace-list");
    if (!container) return;
    container.innerHTML = workspaces.length
      ? workspaces.map((item) => `
        <div class="row-card">
          <strong>${this.escape(item.name)}</strong>
          <p>Page ${this.escape(item.active_tab || "overview")} | Materials ${(item.selected_material_ids || []).length}</p>
          <small>${this.escape(this.describeFilters(item.filters || {}))}</small>
          <div class="row-actions">
            <button type="button" class="mini-action" data-resume-workspace="${item.workspace_id}">Resume context</button>
          </div>
        </div>`).join("")
      : `<div class="row-card"><p>No workspaces saved yet.</p></div>`;
    container.querySelectorAll("[data-resume-workspace]").forEach((button) => {
      button.addEventListener("click", () => onResume(button.dataset.resumeWorkspace));
    });
  },

  applyScenarioVisibility(type) {
    const fields = {
      "scenario-supplier": ["supplier_outage"],
      "scenario-regulation": ["regulation_activation"],
      "scenario-metric": ["reformulation_target"],
      "scenario-target-value": ["reformulation_target"],
      "scenario-max-cost": ["cost_constraint"],
      "scenario-percent-increase": ["cost_constraint"],
    };
    Object.entries(fields).forEach(([id, visibleFor]) => {
      const element = document.getElementById(id);
      if (!element || !element.parentElement) return;
      element.parentElement.classList.toggle("scenario-field-hidden", !visibleFor.includes(type));
    });
  },

  describeFilters(filters) {
    const active = Object.entries(filters).filter(([, value]) => value !== "" && value !== null && value !== undefined);
    return active.length ? active.map(([key, value]) => `${key}: ${value}`).join(" | ") : "No filters saved";
  },

  escape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },
};
