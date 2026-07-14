window.PackGraphAnswerPanel = {
  render(panel) {
    const payload = panel || {};
    document.getElementById("answer-panel-title").textContent = payload.title || "Decision output";
    document.getElementById("answer-panel-summary").textContent = payload.summary || "No summary available.";
    this.renderList("answer-panel-recommendations", payload.recommendations, "No recommendations yet.");
    this.renderList("answer-panel-reasons", payload.reasons, "No supporting reasons yet.");
    this.renderList("answer-panel-risks", payload.risk_flags, "No explicit risk flags yet.");
    this.renderList("answer-panel-next-steps", payload.next_steps, "No next steps yet.");
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

  escape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },
};
