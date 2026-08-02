window.PackGraphAnswerPanel = {
  render(panel) {
    const payload = panel?.panel || panel || {};
    const meta = panel?.meta || payload.meta || {};
    document.getElementById("answer-panel-title").textContent = payload.title || "Decision output";
    document.getElementById("answer-panel-summary").textContent = payload.summary || "No summary available.";
    this.renderList("answer-panel-recommendations", payload.recommendations, "No recommendations yet.");
    this.renderList("answer-panel-reasons", payload.reasons, "No supporting reasons yet.");
    this.renderList("answer-panel-risks", payload.risk_flags, "No explicit risk flags yet.");
    this.renderList("answer-panel-next-steps", payload.next_steps, "No next steps yet.");
    this.renderMeta(meta);
  },

  renderList(id, items, emptyMessage) {
    const container = document.getElementById(id);
    if (!container) return;
    const normalized = Array.isArray(items) ? items : [];
    container.innerHTML = normalized.length
      ? normalized.map((item) => {
        if (typeof item === "string") {
          return `<div class="row-card"><strong>${this.escape(item)}</strong></div>`;
        }
        return `<div class="row-card"><strong>${this.escape(item.label || "Item")}</strong><p>${this.escape(item.detail || "")}</p></div>`;
      }).join("")
      : `<div class="row-card"><p>${this.escape(emptyMessage)}</p></div>`;
  },

  renderMeta(meta) {
    const container = document.getElementById("answer-panel-meta");
    if (!container) return;
    const items = [
      { label: "Recommendation confidence", value: meta.confidence || "Pending" },
      { label: "Evidence strength", value: meta.evidence_strength || "Unknown" },
      { label: "Review state", value: meta.review_state || "Not requested" },
      { label: "Workflow step", value: meta.workflow_step || "Discover" },
    ];
    container.innerHTML = items.map((item) => `
      <div class="status-card answer-meta-card">
        <span>${this.escape(item.label)}</span>
        <strong>${this.escape(item.value)}</strong>
      </div>`).join("");
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
